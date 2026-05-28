"""CQRS投影更新与查询"""

import json
from typing import Any
from uuid import UUID

import asyncpg

from app.hub.events.bus import EventBus


class EventProjections:
    """CQRS读端投影，订阅EventBus事件并更新4张投影表"""

    _MSG_NOT_CONNECTED = "EventProjections未连接，请先调用connect()"

    def __init__(self, event_bus: EventBus, postgres_url: str) -> None:
        self._bus = event_bus
        self._url = postgres_url
        self._pool: asyncpg.Pool | None = None
        self._sub_ids: list[str] = []

    async def connect(self) -> None:
        self._pool = await asyncpg.create_pool(self._url, min_size=2, max_size=10)
        self._sub_ids = [
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

    def _require_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError(self._MSG_NOT_CONNECTED)
        return self._pool

    # -- 投影更新 handler --

    async def _on_message_created(self, payload: dict[str, Any]) -> None:
        pool = self._require_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO thread_messages "
                "(thread_id, project_id, participant_id, participant_type, display_name, content, event_type) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7)",
                UUID(payload["thread_id"]),
                UUID(payload["project_id"]),
                payload["participant_id"],
                payload["participant_type"],
                payload.get("display_name", ""),
                payload["content"],
                payload["event_type"],
            )

    async def _on_summary_generated(self, payload: dict[str, Any]) -> None:
        pool = self._require_pool()
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
                UUID(payload["project_id"]),
                payload["participant_id"],
                payload["participant_type"],
                payload.get("display_name", ""),
                summary_content,
                payload["event_type"],
            )

    async def _on_plan_proposed(self, payload: dict[str, Any]) -> None:
        pool = self._require_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO execution_plans "
                "(id, project_id, thread_id, correlation_id, status, proposed_by, tasks) "
                "VALUES ($1, $2, $3, $4, 'proposed', $5, $6::jsonb)",
                UUID(payload["plan_id"]),
                UUID(payload["project_id"]),
                UUID(payload["thread_id"]) if payload.get("thread_id") else None,
                UUID(payload["correlation_id"]),
                payload["participant_id"],
                json.dumps(payload.get("tasks", [])),
            )

    async def _on_plan_approved(self, payload: dict[str, Any]) -> None:
        pool = self._require_pool()
        async with pool.acquire() as conn:
            # 追加审批者到approved_by列表
            await conn.execute(
                "UPDATE execution_plans "
                "SET status = 'approved', approved_by = approved_by || $1::jsonb, updated_at = NOW() "
                "WHERE id = $2",
                json.dumps([payload["participant_id"]]),
                UUID(payload["plan_id"]),
            )

    async def _on_plan_rejected(self, payload: dict[str, Any]) -> None:
        pool = self._require_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE execution_plans SET status = 'rejected', updated_at = NOW() WHERE id = $1",
                UUID(payload["plan_id"]),
            )

    async def _on_output_generated(self, payload: dict[str, Any]) -> None:
        pool = self._require_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO task_outputs "
                "(id, project_id, task_id, plan_id, output_type, content, diff, file_paths, status) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, 'generated')",
                UUID(payload["output_id"]),
                UUID(payload["project_id"]),
                payload["task_id"],
                UUID(payload["plan_id"]),
                payload["output_type"],
                payload["content"],
                payload.get("diff"),
                json.dumps(payload.get("file_paths", [])),
            )

    async def _on_output_approved(self, payload: dict[str, Any]) -> None:
        pool = self._require_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE task_outputs SET status = 'approved' WHERE id = $1",
                UUID(payload["output_id"]),
            )

    async def _on_output_revision_requested(self, payload: dict[str, Any]) -> None:
        pool = self._require_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE task_outputs SET status = 'revision_requested' WHERE id = $1",
                UUID(payload["output_id"]),
            )

    async def _on_member_added(self, payload: dict[str, Any]) -> None:
        pool = self._require_pool()
        # 幂等：ON CONFLICT不产生重复数据
        # MVP阶段不将payload.roles(str列表)转为DB.roles(BIGINT bitmask)，暂用DB默认0
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO project_members "
                "(participant_id, project_id, type, display_name) "
                "VALUES ($1, $2, $3, $4) "
                "ON CONFLICT (participant_id, project_id) DO NOTHING",
                payload["participant_id"],
                UUID(payload["project_id"]),
                payload["participant_type"],
                payload.get("display_name", ""),
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
