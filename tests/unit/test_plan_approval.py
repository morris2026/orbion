"""步骤15 UT：TC-15.1–15.7 — 执行计划审批API"""

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from app.biz.plans.service import PlanService
from app.hub.events.bus import InProcessEventBus
from app.hub.events.projections import EventProjectionsProtocol
from app.hub.events.store import EventStoreProtocol
from app.hub.events.types import Event, EventType
from app.hub.permissions.bitmask import HumanPermission
from app.hub.permissions.compute import compute_permissions


class MockEventStore(EventStoreProtocol):
    appended: list[Event]

    def __init__(self) -> None:
        self.appended = []

    async def append(self, event: Event) -> None:
        self.appended.append(event)

    async def connect(self) -> None:
        pass

    async def close(self) -> None:
        pass

    async def get_events_by_correlation(self, correlation_id: str, limit: int = 100) -> list[Event]:
        return []

    async def get_events_by_project(
        self, project_id: str, event_type: str | None = None, limit: int = 50
    ) -> list[Event]:
        return []


class MockProjections(EventProjectionsProtocol):
    """内存投影，模拟execution_plans表查询"""

    _plans: list[dict[str, Any]]

    def __init__(self, event_bus: InProcessEventBus) -> None:
        super().__init__(event_bus)
        self._plans = []

    async def connect(self) -> None:
        pass

    async def close(self) -> None:
        pass

    async def get_thread_messages(self, thread_id: str) -> list[dict[str, Any]]:
        return []

    async def get_execution_plans(
        self, project_id: str, thread_id: str | None = None, status: str | None = None
    ) -> list[dict[str, Any]]:
        result = self._plans
        if thread_id is not None:
            result = [p for p in result if p.get("thread_id") == thread_id]
        if status is not None:
            result = [p for p in result if p.get("status") == status]
        return result

    async def get_plan_by_id(self, plan_id: str) -> dict[str, Any] | None:
        for p in self._plans:
            if p.get("id") == plan_id:
                return p
        return None

    async def get_task_outputs(self, project_id: str, plan_id: str | None = None) -> list[dict[str, Any]]:
        return []

    async def get_project_members(self, project_id: str) -> list[dict[str, Any]]:
        return []


def _make_plan_dict(
    plan_id: str = str(uuid.uuid4()),
    project_id: str = "proj-1",
    thread_id: str = "thread-1",
    status: str = "proposed",
    proposed_by: str = "agent-summary-1",
    tasks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """构造内存投影中的计划行"""
    if tasks is None:
        tasks = [
            {"task_id": "t-1", "type": "code", "description": "实现功能A", "dependencies": [], "priority": "high"},
            {
                "task_id": "t-2",
                "type": "document",
                "description": "编写文档B",
                "dependencies": ["t-1"],
                "priority": "medium",
            },
        ]
    return {
        "id": plan_id,
        "project_id": project_id,
        "thread_id": thread_id,
        "correlation_id": "corr-1",
        "status": status,
        "proposed_by": proposed_by,
        "approved_by": [],
        "tasks": tasks,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }


def _make_event(
    event_type: str | EventType,
    project_id: str = "proj-1",
    correlation_id: str = "corr-1",
    payload: dict[str, Any] = {},
) -> Event:
    return Event(
        event_id=str(uuid.uuid4()),
        project_id=project_id,
        event_type=str(event_type),
        participant_id="user-1",
        participant_type="human",
        participant_display_name="Test",
        payload=payload,
        correlation_id=correlation_id,
        created_at=datetime.now(UTC),
    )


def _make_member_roles(project_id: str, user_id: str, roles: int) -> dict[str, Any]:
    """构造内存中的成员行"""
    return {"participant_id": user_id, "project_id": project_id, "roles": roles}


# -- TC-15.1: 计划列表可按thread_id和status过滤 --


async def test_tc15_1_plan_list_filter() -> None:
    """TC-15.1: 创建多个计划（不同thread_id和status）→
    GET /projects/{id}/plans?thread_id=X&status=proposed
    只返回符合条件的计划
    """
    bus = InProcessEventBus()
    store = MockEventStore()
    projections = MockProjections(bus)
    # 写入3个计划：不同thread_id和status组合
    plan_a = _make_plan_dict(plan_id="plan-a", thread_id="thread-1", status="proposed")
    plan_b = _make_plan_dict(plan_id="plan-b", thread_id="thread-2", status="proposed")
    plan_c = _make_plan_dict(plan_id="plan-c", thread_id="thread-1", status="approved")
    projections._plans = [plan_a, plan_b, plan_c]

    service = PlanService(store, bus, projections)
    # 过滤 thread_id=thread-1 + status=proposed
    result = await service.list_plans("proj-1", thread_id="thread-1", status="proposed")
    assert len(result) == 1
    assert result[0]["id"] == "plan-a"


# -- TC-15.2: 部分审批→状态approved+事件发布+投影更新 --


async def test_tc15_2_partial_approve() -> None:
    """TC-15.2: POST approve（只批准部分task_id）→
    计划状态变为approved；approved_tasks只有批准的task；
    EventStore有ExecutionPlanApproved事件
    """
    bus = InProcessEventBus()
    store = MockEventStore()
    projections = MockProjections(bus)
    plan_id = "plan-1"
    plan = _make_plan_dict(plan_id=plan_id, status="proposed")
    projections._plans = [plan]

    service = PlanService(store, bus, projections)
    result = await service.approve_plan(
        plan_id=plan_id,
        approved_tasks=["t-1"],
        modifications=None,
        approver_id="user-1",
        approver_name="TestUser",
        project_id="proj-1",
    )

    assert result["status"] == "approved"
    assert result["approved_tasks"] == ["t-1"]
    # EventStore有ExecutionPlanApproved事件
    assert len(store.appended) == 1
    evt = store.appended[0]
    assert evt.event_type == EventType.ExecutionPlanApproved
    assert evt.payload["plan_id"] == plan_id
    assert evt.payload["approved_tasks"] == ["t-1"]


# -- TC-15.3: 拒绝+修改意见→状态rejected+事件发布 --


async def test_tc15_3_reject_with_suggestions() -> None:
    """TC-15.3: POST reject（reason+suggestions）→
    计划状态变为rejected；EventStore有ExecutionPlanRejected事件；
    reason和suggestions在payload中
    """
    bus = InProcessEventBus()
    store = MockEventStore()
    projections = MockProjections(bus)
    plan_id = "plan-1"
    plan = _make_plan_dict(plan_id=plan_id, status="proposed")
    projections._plans = [plan]

    service = PlanService(store, bus, projections)
    result = await service.reject_plan(
        plan_id=plan_id,
        reason="设计不合理",
        suggestions=["简化流程", "减少依赖"],
        rejecter_id="user-1",
        rejecter_name="TestUser",
        project_id="proj-1",
    )

    assert result["status"] == "rejected"
    assert result["reason"] == "设计不合理"
    assert result["suggestions"] == ["简化流程", "减少依赖"]
    # EventStore有ExecutionPlanRejected事件
    assert len(store.appended) == 1
    evt = store.appended[0]
    assert evt.event_type == EventType.ExecutionPlanRejected
    assert evt.payload["plan_id"] == plan_id
    assert evt.payload["reason"] == "设计不合理"
    assert evt.payload["suggestions"] == ["简化流程", "减少依赖"]


# -- TC-15.4: APPROVE_PLAN权限位检查 --


async def test_tc15_4_approve_permission_check() -> None:
    """TC-15.4: Viewer角色用户 → POST /plans/{id}/approve → 返回403"""
    # Viewer只有VIEW_DISCUSSION权限(bit 0)
    viewer_roles = HumanPermission.VIEW_DISCUSSION
    assert not compute_permissions(viewer_roles, HumanPermission.APPROVE_PLAN)


# -- TC-15.5: 计划状态机proposed→approved/rejected --


async def test_tc15_5_state_machine() -> None:
    """TC-15.5: proposed计划 → approve → 状态approved；
    proposed计划 → reject → 状态rejected
    """
    bus = InProcessEventBus()
    store = MockEventStore()
    projections = MockProjections(bus)

    # approve路径
    plan_a = _make_plan_dict(plan_id="plan-a", status="proposed")
    projections._plans = [plan_a]
    service = PlanService(store, bus, projections)
    result = await service.approve_plan(
        plan_id="plan-a",
        approved_tasks=["t-1"],
        modifications=None,
        approver_id="user-1",
        approver_name="TestUser",
        project_id="proj-1",
    )
    assert result["status"] == "approved"

    # reject路径
    store2 = MockEventStore()
    projections2 = MockProjections(bus)
    plan_b = _make_plan_dict(plan_id="plan-b", status="proposed")
    projections2._plans = [plan_b]
    service2 = PlanService(store2, bus, projections2)
    result2 = await service2.reject_plan(
        plan_id="plan-b",
        reason="不合适",
        suggestions=[],
        rejecter_id="user-1",
        rejecter_name="TestUser",
        project_id="proj-1",
    )
    assert result2["status"] == "rejected"


# -- TC-15.6: REJECT_PLAN权限位验证 --


async def test_tc15_6_reject_permission_check() -> None:
    """TC-15.6: Viewer角色 POST reject → 403（需REJECT_PLAN权限位，
    Viewer只有VIEW_DISCUSSION）
    """
    viewer_roles = HumanPermission.VIEW_DISCUSSION
    assert not compute_permissions(viewer_roles, HumanPermission.REJECT_PLAN)


# -- TC-15.7: 计划错误路径 --


async def test_tc15_7_error_paths() -> None:
    """TC-15.7: 对已approved计划再次approve → 非法状态转换抛ValueError；
    对不存在的plan_id调用approve → 抛ValueError；
    对已rejected计划再次reject → 非法状态转换抛ValueError
    """
    bus = InProcessEventBus()
    store = MockEventStore()
    projections = MockProjections(bus)

    # 已approved计划再次approve
    plan_approved = _make_plan_dict(plan_id="plan-1", status="approved")
    projections._plans = [plan_approved]
    service = PlanService(store, bus, projections)

    with pytest.raises(ValueError, match="非法状态转换"):
        await service.approve_plan(
            plan_id="plan-1",
            approved_tasks=["t-1"],
            modifications=None,
            approver_id="user-1",
            approver_name="TestUser",
            project_id="proj-1",
        )

    # 不存在的plan_id
    with pytest.raises(ValueError, match="计划不存在"):
        await service.approve_plan(
            plan_id="plan-nonexist",
            approved_tasks=["t-1"],
            modifications=None,
            approver_id="user-1",
            approver_name="TestUser",
            project_id="proj-1",
        )

    # 已rejected计划再次reject
    plan_rejected = _make_plan_dict(plan_id="plan-2", status="rejected")
    projections._plans = [plan_approved, plan_rejected]

    with pytest.raises(ValueError, match="非法状态转换"):
        await service.reject_plan(
            plan_id="plan-2",
            reason="再次拒绝",
            suggestions=[],
            rejecter_id="user-1",
            rejecter_name="TestUser",
            project_id="proj-1",
        )
