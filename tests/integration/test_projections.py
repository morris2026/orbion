"""TC-5.1–TC-5.11: CQRS投影更新与查询"""

from collections.abc import AsyncGenerator
from typing import Any, Literal
from uuid import UUID, uuid4

import asyncpg
import pytest

from app.config import Settings
from app.hub.events.bus import InProcessEventBus
from app.hub.events.projections import EventProjections
from app.hub.events.store import EventStore
from app.hub.events.types import Event


@pytest.fixture
async def db_pool() -> AsyncGenerator[asyncpg.Pool, None]:
    """创建数据库连接池"""
    settings = Settings()
    pool = await asyncpg.create_pool(settings.postgres_url, min_size=2, max_size=10)
    yield pool
    await pool.close()


@pytest.fixture
async def event_bus() -> InProcessEventBus:
    """创建InProcessEventBus实例"""
    return InProcessEventBus()


@pytest.fixture
async def event_store(db_pool: asyncpg.Pool) -> EventStore:
    """创建已连接的EventStore"""
    store = EventStore(Settings().postgres_url)
    await store.connect()
    return store


@pytest.fixture
async def projections(event_bus: InProcessEventBus, db_pool: asyncpg.Pool) -> AsyncGenerator[EventProjections, None]:
    """创建EventProjections实例，注册为EventBus subscriber"""
    settings = Settings()
    proj = EventProjections(event_bus, settings.postgres_url)
    await proj.connect()
    yield proj
    await proj.close()


@pytest.fixture
async def clean_tables(db_pool: asyncpg.Pool) -> asyncpg.Pool:
    """清空投影表和event_log，确保测试数据隔离"""
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM task_outputs")
        await conn.execute("DELETE FROM execution_plans")
        await conn.execute("DELETE FROM thread_messages")
        await conn.execute("DELETE FROM project_members")
        await conn.execute("DELETE FROM threads")
        await conn.execute("DELETE FROM projects")
        await conn.execute("DELETE FROM event_log")
    return db_pool


def make_event(
    event_type: str,
    project_id: str | None = None,
    participant_id: str = "user-1",
    participant_type: Literal["human", "agent"] = "human",
    payload: dict[str, Any] | None = None,
    correlation_id: str | None = None,
    causation_id: str | None = None,
) -> Event:
    """构造测试Event实例"""
    return Event(
        event_id=str(uuid4()),
        project_id=project_id or str(uuid4()),
        event_type=event_type,
        participant_id=participant_id,
        participant_type=participant_type,
        payload=payload or {},
        correlation_id=correlation_id or str(uuid4()),
        causation_id=causation_id,
    )


async def seed_project(db_pool: asyncpg.Pool, project_id: str, name: str = "测试项目") -> None:
    """向projects表插入测试项目"""
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO projects (id, name) VALUES ($1, $2)",
            UUID(project_id),
            name,
        )


async def seed_thread(db_pool: asyncpg.Pool, thread_id: str, project_id: str, created_by: str = "user-1") -> None:
    """向threads表插入测试线程"""
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO threads (id, project_id, title, created_by) VALUES ($1, $2, $3, $4)",
            UUID(thread_id),
            UUID(project_id),
            "测试线程",
            created_by,
        )


class TestDiscussionMessageCreatedProjection:
    """TC-5.1: DiscussionMessageCreated → thread_messages投影"""

    async def test_message_created_updates_thread_messages(
        self,
        clean_tables: asyncpg.Pool,
        db_pool: asyncpg.Pool,
        event_bus: InProcessEventBus,
        event_store: EventStore,
        projections: EventProjections,
    ) -> None:
        project_id = str(uuid4())
        thread_id = str(uuid4())
        await seed_project(db_pool, project_id)
        await seed_thread(db_pool, thread_id, project_id)

        payload = {
            "thread_id": thread_id,
            "content": "讨论内容",
            "request_summary": False,
        }
        event = make_event(
            event_type="DiscussionMessageCreated",
            project_id=project_id,
            participant_id="user-1",
            participant_type="human",
            payload=payload,
        )
        await event_store.append(event)
        await event_bus.publish(
            "DiscussionMessageCreated",
            {
                "event_id": event.event_id,
                "project_id": event.project_id,
                "participant_id": event.participant_id,
                "participant_type": event.participant_type,
                "event_type": event.event_type,
                **payload,
            },
        )

        # 等待异步handler执行
        await event_bus.wait_for_pending()

        result = await projections.get_thread_messages(thread_id)

        assert len(result) == 1
        msg = result[0]
        assert msg["participant_id"] == "user-1"
        assert msg["content"] == "讨论内容"
        assert msg["event_type"] == "DiscussionMessageCreated"
        assert msg["project_id"] == project_id


class TestDiscussionSummaryGeneratedProjection:
    """TC-5.2: DiscussionSummaryGenerated → thread_messages投影"""

    async def test_summary_generated_updates_thread_messages(
        self,
        clean_tables: asyncpg.Pool,
        db_pool: asyncpg.Pool,
        event_bus: InProcessEventBus,
        event_store: EventStore,
        projections: EventProjections,
    ) -> None:
        project_id = str(uuid4())
        thread_id = str(uuid4())
        await seed_project(db_pool, project_id)
        await seed_thread(db_pool, thread_id, project_id)

        payload = {
            "thread_id": thread_id,
            "summary_id": str(uuid4()),
            "consensus_points": ["共识1"],
            "divergence_points": ["分歧1"],
            "action_items": ["行动1"],
            "knowledge_references": ["参考1"],
        }
        event = make_event(
            event_type="DiscussionSummaryGenerated",
            project_id=project_id,
            participant_id="agent-summarizer",
            participant_type="agent",
            payload=payload,
        )
        await event_store.append(event)
        await event_bus.publish(
            "DiscussionSummaryGenerated",
            {
                "event_id": event.event_id,
                "project_id": event.project_id,
                "participant_id": event.participant_id,
                "participant_type": event.participant_type,
                "event_type": event.event_type,
                **payload,
            },
        )

        await event_bus.wait_for_pending()

        result = await projections.get_thread_messages(thread_id)

        assert len(result) == 1
        msg = result[0]
        assert msg["participant_type"] == "agent"
        assert msg["event_type"] == "DiscussionSummaryGenerated"
        assert msg["participant_id"] == "agent-summarizer"


class TestExecutionPlanProposedProjection:
    """TC-5.3: ExecutionPlanProposed → execution_plans投影"""

    async def test_plan_proposed_creates_execution_plan(
        self,
        clean_tables: asyncpg.Pool,
        db_pool: asyncpg.Pool,
        event_bus: InProcessEventBus,
        event_store: EventStore,
        projections: EventProjections,
    ) -> None:
        project_id = str(uuid4())
        thread_id = str(uuid4())
        await seed_project(db_pool, project_id)
        await seed_thread(db_pool, thread_id, project_id)

        plan_id = str(uuid4())
        payload = {
            "plan_id": plan_id,
            "thread_id": thread_id,
            "tasks": [
                {
                    "task_id": "task-1",
                    "type": "code",
                    "description": "实现功能",
                    "dependencies": [],
                    "priority": "high",
                },
            ],
        }
        event = make_event(
            event_type="ExecutionPlanProposed",
            project_id=project_id,
            participant_id="agent-planner",
            participant_type="agent",
            payload=payload,
        )
        await event_store.append(event)
        await event_bus.publish(
            "ExecutionPlanProposed",
            {
                "event_id": event.event_id,
                "project_id": event.project_id,
                "participant_id": event.participant_id,
                "participant_type": event.participant_type,
                "event_type": event.event_type,
                "correlation_id": event.correlation_id,
                **payload,
            },
        )

        await event_bus.wait_for_pending()

        result = await projections.get_execution_plans(project_id)

        assert len(result) == 1
        plan = result[0]
        assert plan["status"] == "proposed"
        assert plan["proposed_by"] == "agent-planner"
        tasks = plan["tasks"]
        assert isinstance(tasks, list)
        assert len(tasks) == 1
        assert tasks[0]["task_id"] == "task-1"


class TestExecutionPlanApprovedProjection:
    """TC-5.4: ExecutionPlanApproved → execution_plans状态变更"""

    async def test_plan_approved_updates_status(
        self,
        clean_tables: asyncpg.Pool,
        db_pool: asyncpg.Pool,
        event_bus: InProcessEventBus,
        event_store: EventStore,
        projections: EventProjections,
    ) -> None:
        project_id = str(uuid4())
        thread_id = str(uuid4())
        await seed_project(db_pool, project_id)
        await seed_thread(db_pool, thread_id, project_id)

        plan_id = str(uuid4())
        # 先创建proposed计划
        proposed_payload = {
            "plan_id": plan_id,
            "thread_id": thread_id,
            "tasks": [
                {"task_id": "task-1", "type": "code", "description": "实现", "dependencies": [], "priority": "high"}
            ],
        }
        proposed_event = make_event(
            event_type="ExecutionPlanProposed",
            project_id=project_id,
            participant_id="agent-planner",
            participant_type="agent",
            payload=proposed_payload,
        )
        await event_store.append(proposed_event)
        await event_bus.publish(
            "ExecutionPlanProposed",
            {
                "event_id": proposed_event.event_id,
                "project_id": proposed_event.project_id,
                "participant_id": proposed_event.participant_id,
                "participant_type": proposed_event.participant_type,
                "event_type": proposed_event.event_type,
                "correlation_id": proposed_event.correlation_id,
                **proposed_payload,
            },
        )

        await event_bus.wait_for_pending()

        # 审批通过
        approved_payload = {
            "plan_id": plan_id,
            "approved_tasks": ["task-1"],
            "modifications": None,
        }
        approved_event = make_event(
            event_type="ExecutionPlanApproved",
            project_id=project_id,
            participant_id="user-1",
            participant_type="human",
            payload=approved_payload,
            correlation_id=proposed_event.correlation_id,
            causation_id=proposed_event.event_id,
        )
        await event_store.append(approved_event)
        await event_bus.publish(
            "ExecutionPlanApproved",
            {
                "event_id": approved_event.event_id,
                "project_id": approved_event.project_id,
                "participant_id": approved_event.participant_id,
                "participant_type": approved_event.participant_type,
                "event_type": approved_event.event_type,
                **approved_payload,
            },
        )

        await event_bus.wait_for_pending()

        result = await projections.get_execution_plans(project_id)
        assert len(result) == 1
        plan = result[0]
        assert plan["status"] == "approved"
        assert "user-1" in plan["approved_by"]


class TestExecutionPlanRejectedProjection:
    """TC-5.5: ExecutionPlanRejected → execution_plans状态变更"""

    async def test_plan_rejected_updates_status(
        self,
        clean_tables: asyncpg.Pool,
        db_pool: asyncpg.Pool,
        event_bus: InProcessEventBus,
        event_store: EventStore,
        projections: EventProjections,
    ) -> None:
        project_id = str(uuid4())
        thread_id = str(uuid4())
        await seed_project(db_pool, project_id)
        await seed_thread(db_pool, thread_id, project_id)

        plan_id = str(uuid4())
        proposed_payload = {
            "plan_id": plan_id,
            "thread_id": thread_id,
            "tasks": [
                {"task_id": "task-1", "type": "code", "description": "实现", "dependencies": [], "priority": "high"}
            ],
        }
        proposed_event = make_event(
            event_type="ExecutionPlanProposed",
            project_id=project_id,
            participant_id="agent-planner",
            participant_type="agent",
            payload=proposed_payload,
        )
        await event_store.append(proposed_event)
        await event_bus.publish(
            "ExecutionPlanProposed",
            {
                "event_id": proposed_event.event_id,
                "project_id": proposed_event.project_id,
                "participant_id": proposed_event.participant_id,
                "participant_type": proposed_event.participant_type,
                "event_type": proposed_event.event_type,
                "correlation_id": proposed_event.correlation_id,
                **proposed_payload,
            },
        )

        await event_bus.wait_for_pending()

        # 拒绝
        rejected_payload = {
            "plan_id": plan_id,
            "reason": "不够详细",
            "suggestions": ["补充更多细节"],
        }
        rejected_event = make_event(
            event_type="ExecutionPlanRejected",
            project_id=project_id,
            participant_id="user-1",
            participant_type="human",
            payload=rejected_payload,
            correlation_id=proposed_event.correlation_id,
            causation_id=proposed_event.event_id,
        )
        await event_store.append(rejected_event)
        await event_bus.publish(
            "ExecutionPlanRejected",
            {
                "event_id": rejected_event.event_id,
                "project_id": rejected_event.project_id,
                "participant_id": rejected_event.participant_id,
                "participant_type": rejected_event.participant_type,
                "event_type": rejected_event.event_type,
                **rejected_payload,
            },
        )

        await event_bus.wait_for_pending()

        result = await projections.get_execution_plans(project_id)
        assert len(result) == 1
        assert result[0]["status"] == "rejected"


class TestTaskOutputGeneratedProjection:
    """TC-5.6: TaskOutputGenerated → task_outputs投影"""

    async def test_output_generated_creates_task_output(
        self,
        clean_tables: asyncpg.Pool,
        db_pool: asyncpg.Pool,
        event_bus: InProcessEventBus,
        event_store: EventStore,
        projections: EventProjections,
    ) -> None:
        project_id = str(uuid4())
        thread_id = str(uuid4())
        plan_id = str(uuid4())
        await seed_project(db_pool, project_id)
        await seed_thread(db_pool, thread_id, project_id)

        # 先创建proposed计划（task_outputs需要plan_id存在）
        proposed_payload = {
            "plan_id": plan_id,
            "thread_id": thread_id,
            "tasks": [
                {"task_id": "task-1", "type": "code", "description": "实现", "dependencies": [], "priority": "high"}
            ],
        }
        proposed_event = make_event(
            event_type="ExecutionPlanProposed",
            project_id=project_id,
            participant_id="agent-planner",
            payload=proposed_payload,
        )
        await event_store.append(proposed_event)
        await event_bus.publish(
            "ExecutionPlanProposed",
            {
                "event_id": proposed_event.event_id,
                "project_id": proposed_event.project_id,
                "participant_id": proposed_event.participant_id,
                "participant_type": proposed_event.participant_type,
                "event_type": proposed_event.event_type,
                "correlation_id": proposed_event.correlation_id,
                **proposed_payload,
            },
        )

        await event_bus.wait_for_pending()

        # 产出
        output_payload = {
            "task_id": "task-1",
            "plan_id": plan_id,
            "output_id": str(uuid4()),
            "output_type": "code",
            "content": "print('hello')",
            "diff": "--- a/main.py\n+++ b/main.py",
            "file_paths": ["main.py"],
        }
        output_event = make_event(
            event_type="TaskOutputGenerated",
            project_id=project_id,
            participant_id="agent-executor",
            participant_type="agent",
            payload=output_payload,
            correlation_id=proposed_event.correlation_id,
            causation_id=proposed_event.event_id,
        )
        await event_store.append(output_event)
        await event_bus.publish(
            "TaskOutputGenerated",
            {
                "event_id": output_event.event_id,
                "project_id": output_event.project_id,
                "participant_id": output_event.participant_id,
                "participant_type": output_event.participant_type,
                "event_type": output_event.event_type,
                **output_payload,
            },
        )

        await event_bus.wait_for_pending()

        result = await projections.get_task_outputs(project_id)
        assert len(result) == 1
        output = result[0]
        assert output["status"] == "generated"
        assert output["output_type"] == "code"
        assert output["diff"] == "--- a/main.py\n+++ b/main.py"
        file_paths = output["file_paths"]
        assert isinstance(file_paths, list)
        assert "main.py" in file_paths


class TestTaskOutputApprovedRevisionRequestedProjection:
    """TC-5.7: TaskOutputApproved/RevisionRequested → task_outputs状态变更"""

    async def test_output_approved_updates_status(
        self,
        clean_tables: asyncpg.Pool,
        db_pool: asyncpg.Pool,
        event_bus: InProcessEventBus,
        event_store: EventStore,
        projections: EventProjections,
    ) -> None:
        project_id = str(uuid4())
        thread_id = str(uuid4())
        plan_id = str(uuid4())
        output_id = str(uuid4())
        await seed_project(db_pool, project_id)
        await seed_thread(db_pool, thread_id, project_id)

        # 创建proposed计划
        proposed_event = make_event(
            event_type="ExecutionPlanProposed",
            project_id=project_id,
            payload={
                "plan_id": plan_id,
                "thread_id": thread_id,
                "tasks": [
                    {"task_id": "task-1", "type": "code", "description": "实现", "dependencies": [], "priority": "high"}
                ],
            },
        )
        await event_store.append(proposed_event)
        await event_bus.publish(
            "ExecutionPlanProposed",
            {
                "event_id": proposed_event.event_id,
                "project_id": proposed_event.project_id,
                "participant_id": proposed_event.participant_id,
                "participant_type": proposed_event.participant_type,
                "event_type": proposed_event.event_type,
                "correlation_id": proposed_event.correlation_id,
                "plan_id": plan_id,
                "thread_id": thread_id,
                "tasks": [
                    {"task_id": "task-1", "type": "code", "description": "实现", "dependencies": [], "priority": "high"}
                ],
            },
        )

        await event_bus.wait_for_pending()

        # 创建产出
        output_event = make_event(
            event_type="TaskOutputGenerated",
            project_id=project_id,
            participant_id="agent-executor",
            participant_type="agent",
            payload={
                "task_id": "task-1",
                "plan_id": plan_id,
                "output_id": output_id,
                "output_type": "code",
                "content": "code",
                "diff": None,
                "file_paths": [],
            },
            correlation_id=proposed_event.correlation_id,
            causation_id=proposed_event.event_id,
        )
        await event_store.append(output_event)
        await event_bus.publish(
            "TaskOutputGenerated",
            {
                "event_id": output_event.event_id,
                "project_id": output_event.project_id,
                "participant_id": output_event.participant_id,
                "participant_type": output_event.participant_type,
                "event_type": output_event.event_type,
                "task_id": "task-1",
                "plan_id": plan_id,
                "output_id": output_id,
                "output_type": "code",
                "content": "code",
                "diff": None,
                "file_paths": [],
            },
        )

        await event_bus.wait_for_pending()

        # 审批通过
        approved_event = make_event(
            event_type="TaskOutputApproved",
            project_id=project_id,
            participant_id="user-1",
            participant_type="human",
            payload={"output_id": output_id, "feedback": "不错"},
            correlation_id=proposed_event.correlation_id,
            causation_id=output_event.event_id,
        )
        await event_store.append(approved_event)
        await event_bus.publish(
            "TaskOutputApproved",
            {
                "event_id": approved_event.event_id,
                "project_id": approved_event.project_id,
                "participant_id": approved_event.participant_id,
                "participant_type": approved_event.participant_type,
                "event_type": approved_event.event_type,
                "output_id": output_id,
                "feedback": "不错",
            },
        )

        await event_bus.wait_for_pending()

        result = await projections.get_task_outputs(project_id)
        assert len(result) == 1
        assert result[0]["status"] == "approved"

    async def test_revision_requested_updates_status(
        self,
        clean_tables: asyncpg.Pool,
        db_pool: asyncpg.Pool,
        event_bus: InProcessEventBus,
        event_store: EventStore,
        projections: EventProjections,
    ) -> None:
        project_id = str(uuid4())
        thread_id = str(uuid4())
        plan_id = str(uuid4())
        output_id = str(uuid4())
        await seed_project(db_pool, project_id)
        await seed_thread(db_pool, thread_id, project_id)

        # 创建proposed计划
        proposed_event = make_event(
            event_type="ExecutionPlanProposed",
            project_id=project_id,
            payload={
                "plan_id": plan_id,
                "thread_id": thread_id,
                "tasks": [
                    {"task_id": "task-1", "type": "code", "description": "实现", "dependencies": [], "priority": "high"}
                ],
            },
        )
        await event_store.append(proposed_event)
        await event_bus.publish(
            "ExecutionPlanProposed",
            {
                "event_id": proposed_event.event_id,
                "project_id": proposed_event.project_id,
                "participant_id": proposed_event.participant_id,
                "participant_type": proposed_event.participant_type,
                "event_type": proposed_event.event_type,
                "correlation_id": proposed_event.correlation_id,
                "plan_id": plan_id,
                "thread_id": thread_id,
                "tasks": [
                    {"task_id": "task-1", "type": "code", "description": "实现", "dependencies": [], "priority": "high"}
                ],
            },
        )

        await event_bus.wait_for_pending()

        # 创建产出
        output_event = make_event(
            event_type="TaskOutputGenerated",
            project_id=project_id,
            participant_id="agent-executor",
            participant_type="agent",
            payload={
                "task_id": "task-1",
                "plan_id": plan_id,
                "output_id": output_id,
                "output_type": "code",
                "content": "code",
                "diff": None,
                "file_paths": [],
            },
            correlation_id=proposed_event.correlation_id,
            causation_id=proposed_event.event_id,
        )
        await event_store.append(output_event)
        await event_bus.publish(
            "TaskOutputGenerated",
            {
                "event_id": output_event.event_id,
                "project_id": output_event.project_id,
                "participant_id": output_event.participant_id,
                "participant_type": output_event.participant_type,
                "event_type": output_event.event_type,
                "task_id": "task-1",
                "plan_id": plan_id,
                "output_id": output_id,
                "output_type": "code",
                "content": "code",
                "diff": None,
                "file_paths": [],
            },
        )

        await event_bus.wait_for_pending()

        # 要求修改
        revision_event = make_event(
            event_type="TaskOutputRevisionRequested",
            project_id=project_id,
            participant_id="user-1",
            participant_type="human",
            payload={"output_id": output_id, "task_id": "task-1", "issues": ["有bug"], "suggestions": ["修复bug"]},
            correlation_id=proposed_event.correlation_id,
            causation_id=output_event.event_id,
        )
        await event_store.append(revision_event)
        await event_bus.publish(
            "TaskOutputRevisionRequested",
            {
                "event_id": revision_event.event_id,
                "project_id": revision_event.project_id,
                "participant_id": revision_event.participant_id,
                "participant_type": revision_event.participant_type,
                "event_type": revision_event.event_type,
                "output_id": output_id,
                "task_id": "task-1",
                "issues": ["有bug"],
                "suggestions": ["修复bug"],
            },
        )

        await event_bus.wait_for_pending()

        result = await projections.get_task_outputs(project_id)
        assert len(result) == 1
        assert result[0]["status"] == "revision_requested"


class TestProjectMembersProjection:
    """TC-5.8: 成员添加 → project_members投影"""

    async def test_member_added_updates_project_members(
        self,
        clean_tables: asyncpg.Pool,
        db_pool: asyncpg.Pool,
        event_bus: InProcessEventBus,
        event_store: EventStore,
        projections: EventProjections,
    ) -> None:
        project_id = str(uuid4())
        await seed_project(db_pool, project_id)

        payload = {
            "participant_id": "user-1",
            "project_id": project_id,
            "participant_type": "human",
            "display_name": "张三",
            "roles": ["owner"],
        }
        event = make_event(
            event_type="MemberAdded",
            project_id=project_id,
            participant_id="user-1",
            participant_type="human",
            payload=payload,
        )
        await event_store.append(event)
        await event_bus.publish(
            "MemberAdded",
            {
                "event_id": event.event_id,
                "project_id": event.project_id,
                "participant_id": event.participant_id,
                "participant_type": event.participant_type,
                "event_type": event.event_type,
                **payload,
            },
        )

        await event_bus.wait_for_pending()

        result = await projections.get_project_members(project_id)
        assert len(result) == 1
        member = result[0]
        assert member["participant_id"] == "user-1"
        assert member["project_id"] == project_id
        assert member["type"] == "human"
        assert member["display_name"] == "张三"
        # MVP阶段roles未做str→bitmask转换，DB默认0
        assert member["roles"] == 0


class TestProjectionQueryStructuredData:
    """TC-5.9: 投影查询返回结构化数据"""

    async def test_queries_return_structured_dicts(
        self,
        clean_tables: asyncpg.Pool,
        db_pool: asyncpg.Pool,
        event_bus: InProcessEventBus,
        event_store: EventStore,
        projections: EventProjections,
    ) -> None:
        project_id = str(uuid4())
        thread_id = str(uuid4())
        await seed_project(db_pool, project_id)
        await seed_thread(db_pool, thread_id, project_id)

        payload = {
            "thread_id": thread_id,
            "content": "测试消息",
            "request_summary": False,
        }
        event = make_event(
            event_type="DiscussionMessageCreated",
            project_id=project_id,
            payload=payload,
        )
        await event_store.append(event)
        await event_bus.publish(
            "DiscussionMessageCreated",
            {
                "event_id": event.event_id,
                "project_id": event.project_id,
                "participant_id": event.participant_id,
                "participant_type": event.participant_type,
                "event_type": event.event_type,
                **payload,
            },
        )

        await event_bus.wait_for_pending()

        result = await projections.get_thread_messages(thread_id)
        assert len(result) == 1
        msg = result[0]
        # 返回结构化dict，字段名和类型可直接用于前端响应
        assert isinstance(msg, dict)
        assert "id" in msg
        assert "thread_id" in msg
        assert "project_id" in msg
        assert "participant_id" in msg
        assert "participant_type" in msg
        assert "content" in msg
        assert "event_type" in msg
        assert "created_at" in msg


class TestCorrelationIdChainTracking:
    """TC-5.10: correlation_id多跳链路追踪"""

    async def test_correlation_chain_tracks_full_collaboration(
        self,
        clean_tables: asyncpg.Pool,
        event_store: EventStore,
    ) -> None:
        correlation_id = str(uuid4())

        # 写入5跳协作链
        msg_event = make_event(
            event_type="DiscussionMessageCreated",
            correlation_id=correlation_id,
        )
        await event_store.append(msg_event)

        summary_event = make_event(
            event_type="DiscussionSummaryGenerated",
            correlation_id=correlation_id,
            causation_id=msg_event.event_id,
        )
        await event_store.append(summary_event)

        plan_event = make_event(
            event_type="ExecutionPlanProposed",
            correlation_id=correlation_id,
            causation_id=summary_event.event_id,
        )
        await event_store.append(plan_event)

        approved_event = make_event(
            event_type="ExecutionPlanApproved",
            correlation_id=correlation_id,
            causation_id=plan_event.event_id,
        )
        await event_store.append(approved_event)

        output_event = make_event(
            event_type="TaskOutputGenerated",
            correlation_id=correlation_id,
            causation_id=approved_event.event_id,
        )
        await event_store.append(output_event)

        result = await event_store.get_events_by_correlation(correlation_id)

        assert len(result) == 5
        assert all(e.correlation_id == correlation_id for e in result)
        # causation_id指向上一跳
        assert result[1].causation_id == msg_event.event_id
        assert result[2].causation_id == summary_event.event_id
        assert result[3].causation_id == plan_event.event_id
        assert result[4].causation_id == approved_event.event_id


class TestProjectMembersPrimaryKeyConstraint:
    """TC-5.11: project_members联合主键约束"""

    async def test_duplicate_member_insert_is_idempotent(
        self,
        clean_tables: asyncpg.Pool,
        db_pool: asyncpg.Pool,
        event_bus: InProcessEventBus,
        event_store: EventStore,
        projections: EventProjections,
    ) -> None:
        project_id = str(uuid4())
        await seed_project(db_pool, project_id)

        payload = {
            "participant_id": "user-A",
            "project_id": project_id,
            "participant_type": "human",
            "display_name": "用户A",
            "roles": ["owner"],
        }
        event1 = make_event(
            event_type="MemberAdded",
            project_id=project_id,
            participant_id="user-A",
            payload=payload,
        )
        await event_store.append(event1)
        await event_bus.publish(
            "MemberAdded",
            {
                "event_id": event1.event_id,
                "project_id": event1.project_id,
                "participant_id": event1.participant_id,
                "participant_type": event1.participant_type,
                "event_type": event1.event_type,
                **payload,
            },
        )

        await event_bus.wait_for_pending()

        # 再次写入同一成员到同一项目
        event2 = make_event(
            event_type="MemberAdded",
            project_id=project_id,
            participant_id="user-A",
            payload=payload,
        )
        await event_store.append(event2)
        await event_bus.publish(
            "MemberAdded",
            {
                "event_id": event2.event_id,
                "project_id": event2.project_id,
                "participant_id": event2.participant_id,
                "participant_type": event2.participant_type,
                "event_type": event2.event_type,
                **payload,
            },
        )

        await event_bus.wait_for_pending()

        result = await projections.get_project_members(project_id)
        # 幂等：不产生重复数据
        assert len(result) == 1
