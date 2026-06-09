"""任务产出审批API测试"""

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from app.biz.outputs.service import OutputService
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
    """内存投影，模拟task_outputs表查询"""

    _outputs: list[dict[str, Any]]
    _plans: list[dict[str, Any]]

    def __init__(self, event_bus: InProcessEventBus) -> None:
        super().__init__(event_bus)
        self._outputs = []
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
        return self._plans

    async def get_plan_by_id(self, plan_id: str) -> dict[str, Any] | None:
        for p in self._plans:
            if p.get("id") == plan_id:
                return p
        return None

    async def get_task_outputs(self, project_id: str, plan_id: str | None = None) -> list[dict[str, Any]]:
        result = [o for o in self._outputs if o.get("project_id") == project_id]
        if plan_id is not None:
            result = [o for o in result if o.get("plan_id") == plan_id]
        return result

    async def get_output_by_id(self, output_id: str) -> dict[str, Any] | None:
        for o in self._outputs:
            if o.get("id") == output_id:
                return o
        return None

    async def get_project_members(self, project_id: str) -> list[dict[str, Any]]:
        return []


def _make_output_dict(
    output_id: str = str(uuid.uuid4()),
    project_id: str = "proj-1",
    task_id: str = "t-1",
    plan_id: str = "plan-1",
    output_type: str = "code",
    content: str = "def foo(): pass",
    diff: str | None = None,
    status: str = "generated",
    version: int = 1,
) -> dict[str, Any]:
    """构造内存投影中的产出行"""
    return {
        "id": output_id,
        "project_id": project_id,
        "task_id": task_id,
        "plan_id": plan_id,
        "output_type": output_type,
        "content": content,
        "diff": diff,
        "file_paths": ["src/foo.py"],
        "status": status,
        "version": version,
        "created_at": datetime.now(UTC),
    }


# -- MVP-16.1: 产出列表可按plan_id过滤 --


async def test_tc16_1_output_list_filter() -> None:
    """MVP-16.1: 创建多个产出（不同plan_id）→
    GET /projects/{id}/outputs?plan_id=X → 只返回该plan_id的产出
    """
    bus = InProcessEventBus()
    store = MockEventStore()
    projections = MockProjections(bus)
    out_a = _make_output_dict(output_id="out-a", plan_id="plan-1")
    out_b = _make_output_dict(output_id="out-b", plan_id="plan-2")
    out_c = _make_output_dict(output_id="out-c", plan_id="plan-1")
    projections._outputs = [out_a, out_b, out_c]

    service = OutputService(store, bus, projections)
    result = await service.list_outputs("proj-1", plan_id="plan-1")
    assert len(result) == 2
    assert result[0]["id"] == "out-a"
    assert result[1]["id"] == "out-c"


# -- MVP-16.2: 产出审批通过→状态approved+事件发布 --


async def test_tc16_2_approve_output() -> None:
    """MVP-16.2: POST approve → 产出状态变为approved；
    EventStore有TaskOutputApproved事件
    """
    bus = InProcessEventBus()
    store = MockEventStore()
    projections = MockProjections(bus)
    output_id = "out-1"
    output = _make_output_dict(output_id=output_id, status="generated")
    projections._outputs = [output]

    service = OutputService(store, bus, projections)
    result = await service.approve_output(
        output_id=output_id,
        feedback="代码质量不错",
        approver_id="user-1",
        approver_name="TestUser",
        project_id="proj-1",
    )

    assert result["status"] == "approved"
    assert result["feedback"] == "代码质量不错"
    assert len(store.appended) == 1
    evt = store.appended[0]
    assert evt.event_type == EventType.TaskOutputApproved
    assert evt.payload["output_id"] == output_id
    assert evt.payload["feedback"] == "代码质量不错"


# -- MVP-16.3: 产出要求修改→状态revision_requested+事件发布 --


async def test_tc16_3_request_revision() -> None:
    """MVP-16.3: POST request-revision（issues+suggestions）→
    产出状态变为revision_requested；EventStore有TaskOutputRevisionRequested事件；
    issues和suggestions在payload中
    """
    bus = InProcessEventBus()
    store = MockEventStore()
    projections = MockProjections(bus)
    output_id = "out-1"
    task_id = "t-1"
    output = _make_output_dict(output_id=output_id, task_id=task_id, status="generated")
    projections._outputs = [output]

    service = OutputService(store, bus, projections)
    result = await service.request_revision(
        output_id=output_id,
        issues=["缺少错误处理", "变量命名不规范"],
        suggestions=["添加try/except", "用snake_case命名"],
        requester_id="user-1",
        requester_name="TestUser",
        project_id="proj-1",
    )

    assert result["status"] == "revision_requested"
    assert result["issues"] == ["缺少错误处理", "变量命名不规范"]
    assert result["suggestions"] == ["添加try/except", "用snake_case命名"]
    assert len(store.appended) == 1
    evt = store.appended[0]
    assert evt.event_type == EventType.TaskOutputRevisionRequested
    assert evt.payload["output_id"] == output_id
    assert evt.payload["task_id"] == task_id
    assert evt.payload["issues"] == ["缺少错误处理", "变量命名不规范"]


# -- MVP-16.4: 产出状态机generated→approved/revision_requested --


async def test_tc16_4_state_machine() -> None:
    """MVP-16.4: generated产出→approve→状态approved；
    generated产出→request-revision→状态revision_requested
    """
    bus = InProcessEventBus()

    # approve路径
    store1 = MockEventStore()
    projections1 = MockProjections(bus)
    out_a = _make_output_dict(output_id="out-a", status="generated")
    projections1._outputs = [out_a]
    service1 = OutputService(store1, bus, projections1)
    result = await service1.approve_output(
        output_id="out-a",
        feedback=None,
        approver_id="user-1",
        approver_name="TestUser",
        project_id="proj-1",
    )
    assert result["status"] == "approved"

    # revision路径
    store2 = MockEventStore()
    projections2 = MockProjections(bus)
    out_b = _make_output_dict(output_id="out-b", status="generated")
    projections2._outputs = [out_b]
    service2 = OutputService(store2, bus, projections2)
    result2 = await service2.request_revision(
        output_id="out-b",
        issues=["问题1"],
        suggestions=[],
        requester_id="user-1",
        requester_name="TestUser",
        project_id="proj-1",
    )
    assert result2["status"] == "revision_requested"


# -- MVP-16.5: 产出version自增 --


async def test_tc16_5_version_increment() -> None:
    """MVP-16.5: Agent生成产出（version=1）→ request-revision →
    Agent重新生成产出 → 新产出version=2
    """
    bus = InProcessEventBus()
    store = MockEventStore()
    projections = MockProjections(bus)

    # v1产出
    out_v1 = _make_output_dict(output_id="out-v1", task_id="t-1", status="generated", version=1)
    projections._outputs = [out_v1]

    service = OutputService(store, bus, projections)
    # request-revision on v1
    result = await service.request_revision(
        output_id="out-v1",
        issues=["需改进"],
        suggestions=["优化"],
        requester_id="user-1",
        requester_name="TestUser",
        project_id="proj-1",
    )
    assert result["status"] == "revision_requested"

    # Agent重新生成v2产出——在投影中追加新行
    out_v2 = _make_output_dict(output_id="out-v2", task_id="t-1", status="generated", version=2)
    projections._outputs = [out_v1, out_v2]

    # 列出该task_id的产出，确认v2存在
    outputs = await service.list_outputs("proj-1")
    v2_found = any(o["version"] == 2 and o["task_id"] == "t-1" for o in outputs)
    assert v2_found


# -- MVP-16.6: 产出错误路径 --


async def test_tc16_6_error_paths() -> None:
    """MVP-16.6: 非法状态转换和不存在ID的错误路径"""
    bus = InProcessEventBus()
    store = MockEventStore()
    projections = MockProjections(bus)

    # 已approved产出再次approve
    out_approved = _make_output_dict(output_id="out-1", status="approved")
    projections._outputs = [out_approved]
    service = OutputService(store, bus, projections)

    with pytest.raises(ValueError, match="非法状态转换"):
        await service.approve_output(
            output_id="out-1",
            feedback=None,
            approver_id="user-1",
            approver_name="TestUser",
            project_id="proj-1",
        )

    # 已approved产出 request-revision → 非法状态转换
    with pytest.raises(ValueError, match="非法状态转换"):
        await service.request_revision(
            output_id="out-1",
            issues=["问题1"],
            suggestions=[],
            requester_id="user-1",
            requester_name="TestUser",
            project_id="proj-1",
        )

    # 已revision_requested产出再次approve → 非法状态转换
    out_revisioned = _make_output_dict(output_id="out-2", status="revision_requested")
    projections._outputs = [out_approved, out_revisioned]

    with pytest.raises(ValueError, match="非法状态转换"):
        await service.approve_output(
            output_id="out-2",
            feedback=None,
            approver_id="user-1",
            approver_name="TestUser",
            project_id="proj-1",
        )

    # 已revision_requested产出再次request-revision → 非法状态转换
    with pytest.raises(ValueError, match="非法状态转换"):
        await service.request_revision(
            output_id="out-2",
            issues=["再改"],
            suggestions=[],
            requester_id="user-1",
            requester_name="TestUser",
            project_id="proj-1",
        )

    # 不存在的output_id
    with pytest.raises(ValueError, match="产出不存在"):
        await service.approve_output(
            output_id="out-nonexist",
            feedback=None,
            approver_id="user-1",
            approver_name="TestUser",
            project_id="proj-1",
        )


# -- 权限位验证：approve需APPROVE_PLAN，request-revision需CREATE_MESSAGE --


async def test_tc16_permission_bits() -> None:
    """产出审批权限位：approve需APPROVE_PLAN（Viewer没有）；
    request-revision需CREATE_MESSAGE（Member有）
    """
    viewer_roles = HumanPermission.VIEW_DISCUSSION
    assert not compute_permissions(viewer_roles, HumanPermission.APPROVE_PLAN)

    member_roles = HumanPermission.VIEW_DISCUSSION | HumanPermission.CREATE_MESSAGE | HumanPermission.APPROVE_PLAN
    assert compute_permissions(member_roles, HumanPermission.APPROVE_PLAN)
    assert compute_permissions(member_roles, HumanPermission.CREATE_MESSAGE)
