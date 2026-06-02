"""PostgresEventProjections — PostgreSQL 4张投影表的CQRS读端实现"""

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import asyncpg

from app.config import get_settings
from app.hub.events.bus import EventBus
from app.hub.events.projections import EventProjectionsProtocol
from app.hub.events.types import Event
from app.hub.permissions.roles import AGENT_ROLE_BITS, HUMAN_ROLE_BITS


class PostgresEventProjections(EventProjectionsProtocol):
    """PostgreSQL 4张投影表的CQRS读端实现"""

    _MSG_NOT_CONNECTED = "PostgresEventProjections未连接，请先调用connect()"

    def __init__(self, event_bus: EventBus) -> None:
        super().__init__(event_bus)
        settings = get_settings()
        self._url = settings.postgres.url
        self._pool: asyncpg.Pool | None = None
        self._sub_ids: list[str] = []

    async def connect(self) -> None:
        self._pool = await asyncpg.create_pool(self._url, min_size=2, max_size=10)
        self._sub_ids = [
            self._bus.subscribe("ProjectCreated", self._on_project_created),
            self._bus.subscribe("DiscussionMessageCreated", self._on_message_created),
            self._bus.subscribe("DiscussionSummaryGenerated", self._on_summary_generated),
            self._bus.subscribe("ExecutionPlanProposed", self._on_plan_proposed),
            self._bus.subscribe("ExecutionPlanApproved", self._on_plan_approved),
            self._bus.subscribe("ExecutionPlanRejected", self._on_plan_rejected),
            self._bus.subscribe("TaskOutputGenerated", self._on_output_generated),
            self._bus.subscribe("TaskOutputApproved", self._on_output_approved),
            self._bus.subscribe("TaskOutputRevisionRequested", self._on_output_revision_requested),
            self._bus.subscribe("MemberAdded", self._on_member_added),
        ]

    async def close(self) -> None:
        if self._pool:
            for sub_id in self._sub_ids:
                self._bus.unsubscribe(sub_id)
            await self._pool.close()

    @property
    def pool(self) -> asyncpg.Pool:
        return self._require_pool()

    def _require_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError(self._MSG_NOT_CONNECTED)
        return self._pool

    # -- 投影更新 handler --

    async def _on_project_created(self, event: Event) -> None:
        pool = self._require_pool()
        payload = event.payload
        async with pool.acquire() as conn:
            async with conn.transaction():
                # MVP阶段暂不实现租户隔离，tenant_id由DB DEFAULT填充，投影handler不写入
                await conn.execute(
                    "INSERT INTO projects (id, name, description, created_at) "
                    "VALUES ($1, $2, $3, $4) ON CONFLICT (id) DO NOTHING",
                    UUID(event.project_id),
                    payload["name"],
                    payload.get("description"),
                    event.created_at or datetime.now(UTC),
                )
                # creator 自动成为 owner member（原子事务，FK依赖在事务内解决）
                await conn.execute(
                    "INSERT INTO project_members "
                    "(participant_id, project_id, type, display_name, roles) "
                    "VALUES ($1, $2, 'human', $3, $4) "
                    "ON CONFLICT (participant_id, project_id) DO UPDATE SET "
                    "display_name = EXCLUDED.display_name, roles = EXCLUDED.roles",
                    event.participant_id,
                    UUID(event.project_id),
                    event.participant_display_name,
                    HUMAN_ROLE_BITS["owner"],
                )

    async def _on_message_created(self, event: Event) -> None:
        pool = self._require_pool()
        payload = event.payload
        async with pool.acquire() as conn:
            # message_id用于投影表和响应id对齐，保证游标分页一致性
            message_id = payload.get("message_id")
            if message_id:
                await conn.execute(
                    "INSERT INTO thread_messages "
                    "(id, thread_id, project_id, participant_id, participant_type, display_name, content, event_type) "
                    "VALUES ($1, $2, $3, $4, $5, $6, $7, $8)",
                    UUID(message_id),
                    UUID(payload["thread_id"]),
                    UUID(event.project_id),
                    event.participant_id,
                    event.participant_type,
                    event.participant_display_name,
                    payload["content"],
                    event.event_type,
                )
            else:
                await conn.execute(
                    "INSERT INTO thread_messages "
                    "(thread_id, project_id, participant_id, participant_type, display_name, content, event_type) "
                    "VALUES ($1, $2, $3, $4, $5, $6, $7)",
                    UUID(payload["thread_id"]),
                    UUID(event.project_id),
                    event.participant_id,
                    event.participant_type,
                    event.participant_display_name,
                    payload["content"],
                    event.event_type,
                )

    async def _on_summary_generated(self, event: Event) -> None:
        pool = self._require_pool()
        payload = event.payload
        summary_content = json.dumps(
            {
                "summary_id": payload.get("summary_id"),
                "consensus_points": payload.get("consensus_points", []),
                "divergence_points": payload.get("divergence_points", []),
                "action_items": payload.get("action_items", []),
                "knowledge_references": payload.get("knowledge_references", []),
            }
        )
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO thread_messages "
                "(thread_id, project_id, participant_id, participant_type, display_name, content, event_type) "
                "VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7)",
                UUID(payload["thread_id"]),
                UUID(event.project_id),
                event.participant_id,
                event.participant_type,
                event.participant_display_name,
                summary_content,
                event.event_type,
            )

    async def _on_plan_proposed(self, event: Event) -> None:
        pool = self._require_pool()
        payload = event.payload
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO execution_plans "
                "(id, project_id, thread_id, correlation_id, status, proposed_by, tasks) "
                "VALUES ($1, $2, $3, $4, 'proposed', $5, $6::jsonb)",
                UUID(payload["plan_id"]),
                UUID(event.project_id),
                UUID(payload["thread_id"]) if payload.get("thread_id") else None,
                UUID(event.correlation_id),
                event.participant_id,
                json.dumps(payload.get("tasks", [])),
            )

    async def _on_plan_approved(self, event: Event) -> None:
        pool = self._require_pool()
        payload = event.payload
        async with pool.acquire() as conn:
            # 追加审批者到approved_by列表
            await conn.execute(
                "UPDATE execution_plans "
                "SET status = 'approved', approved_by = approved_by || $1::jsonb, updated_at = NOW() "
                "WHERE id = $2",
                json.dumps([event.participant_id]),
                UUID(payload["plan_id"]),
            )

    async def _on_plan_rejected(self, event: Event) -> None:
        pool = self._require_pool()
        payload = event.payload
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE execution_plans SET status = 'rejected', updated_at = NOW() WHERE id = $1",
                UUID(payload["plan_id"]),
            )

    async def _on_output_generated(self, event: Event) -> None:
        pool = self._require_pool()
        payload = event.payload
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO task_outputs "
                "(id, project_id, task_id, plan_id, output_type, content, diff, file_paths, status) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, 'generated')",
                UUID(payload["output_id"]),
                UUID(event.project_id),
                payload["task_id"],
                UUID(payload["plan_id"]),
                payload["output_type"],
                payload["content"],
                payload.get("diff"),
                json.dumps(payload.get("file_paths", [])),
            )

    async def _on_output_approved(self, event: Event) -> None:
        pool = self._require_pool()
        payload = event.payload
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE task_outputs SET status = 'approved' WHERE id = $1",
                UUID(payload["output_id"]),
            )

    async def _on_output_revision_requested(self, event: Event) -> None:
        pool = self._require_pool()
        payload = event.payload
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE task_outputs SET status = 'revision_requested' WHERE id = $1",
                UUID(payload["output_id"]),
            )

    async def _on_member_added(self, event: Event) -> None:
        pool = self._require_pool()
        payload = event.payload
        roles_bits = _roles_to_bitmask(payload.get("roles", []), event.participant_type)
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO project_members "
                "(participant_id, project_id, type, display_name, roles) "
                "VALUES ($1, $2, $3, $4, $5) "
                "ON CONFLICT (participant_id, project_id) DO UPDATE SET "
                "display_name = EXCLUDED.display_name, roles = EXCLUDED.roles",
                event.participant_id,
                UUID(event.project_id),
                event.participant_type,
                event.participant_display_name,
                roles_bits,
            )

    # -- 投影查询方法 --

    async def get_thread_messages(self, thread_id: str) -> list[dict[str, Any]]:
        pool = self._require_pool()
        rows = await pool.fetch(
            "SELECT id, thread_id, project_id, participant_id, participant_type, "
            "display_name, content, event_type, created_at "
            "FROM thread_messages WHERE thread_id = $1 ORDER BY created_at ASC",
            UUID(thread_id),
        )
        return [_row_to_dict(row) for row in rows]

    async def get_execution_plans(
        self, project_id: str, thread_id: str | None = None, status: str | None = None
    ) -> list[dict[str, Any]]:
        pool = self._require_pool()
        conditions: list[str] = ["project_id = $1"]
        params: list[Any] = [UUID(project_id)]
        idx = 2
        if thread_id is not None:
            conditions.append(f"thread_id = ${idx}")
            params.append(UUID(thread_id))
            idx += 1
        if status is not None:
            conditions.append(f"status = ${idx}")
            params.append(status)
            idx += 1
        where = " AND ".join(conditions)
        rows = await pool.fetch(
            f"SELECT id, project_id, thread_id, correlation_id, status, proposed_by, "
            f"approved_by, tasks, created_at, updated_at "
            f"FROM execution_plans WHERE {where} ORDER BY created_at DESC",
            *params,
        )
        return [_row_to_dict(row) for row in rows]

    async def get_task_outputs(self, project_id: str, plan_id: str | None = None) -> list[dict[str, Any]]:
        pool = self._require_pool()
        if plan_id is not None:
            rows = await pool.fetch(
                "SELECT id, project_id, task_id, plan_id, output_type, content, "
                "diff, file_paths, status, version, created_at "
                "FROM task_outputs WHERE project_id = $1 AND plan_id = $2 "
                "ORDER BY created_at ASC",
                UUID(project_id),
                UUID(plan_id),
            )
        else:
            rows = await pool.fetch(
                "SELECT id, project_id, task_id, plan_id, output_type, content, "
                "diff, file_paths, status, version, created_at "
                "FROM task_outputs WHERE project_id = $1 "
                "ORDER BY created_at ASC",
                UUID(project_id),
            )
        return [_row_to_dict(row) for row in rows]

    async def get_project_members(self, project_id: str) -> list[dict[str, Any]]:
        pool = self._require_pool()
        rows = await pool.fetch(
            "SELECT participant_id, project_id, type, display_name, roles, "
            "agent_type, model_id, status, created_at "
            "FROM project_members WHERE project_id = $1 ORDER BY created_at ASC",
            UUID(project_id),
        )
        return [_row_to_dict(row) for row in rows]


def _row_to_dict(row: asyncpg.Record) -> dict[str, Any]:
    """asyncpg Record → dict，处理UUID和JSONB类型转换"""
    record: dict[str, Any] = dict(row)
    # UUID对象转str
    for key in ("id", "thread_id", "project_id", "plan_id", "correlation_id"):
        if record.get(key) is not None and isinstance(record[key], UUID):
            record[key] = str(record[key])
    # JSONB str → dict/list
    for key in ("tasks", "approved_by", "file_paths"):
        val = record.get(key)
        if isinstance(val, str):
            record[key] = json.loads(val)
    return record


def _roles_to_bitmask(role_names: list[str], participant_type: str) -> int:
    """将角色名称列表转换为权限位掩码"""
    if participant_type == "human":
        bits = 0
        for role in role_names:
            bits |= HUMAN_ROLE_BITS.get(role, HUMAN_ROLE_BITS["member"])
        return bits if bits > 0 else HUMAN_ROLE_BITS["member"]
    bits = 0
    for role in role_names:
        bits |= AGENT_ROLE_BITS.get(role, 0)
    return bits


def _parse_datetime(value: str | datetime) -> datetime:
    """Bus payload中created_at可能是ISO字符串（Pydantic model_dump序列化），需转为datetime"""
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)
