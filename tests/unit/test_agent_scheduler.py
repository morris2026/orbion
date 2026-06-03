"""AgentScheduler调度路由UT/集成：TC-12.2–12.5、TC-12.10"""

from datetime import UTC, datetime
from typing import Any

import pytest

from app.biz.agents.adapters.base import ModelOutput, PromptInput
from app.biz.agents.declarations import DECOMPOSE_DECLARATION, EXECUTE_DECLARATION, SUMMARY_DECLARATION
from app.biz.agents.runtime import AgentRuntime
from app.biz.agents.scheduler import AgentScheduler
from app.hub.events.bus import InProcessEventBus
from app.hub.events.store import EventStoreProtocol
from app.hub.events.types import Event, EventType


class DispatchRecorder:
    """记录dispatch调用的mock adapter"""

    def __init__(self) -> None:
        self.dispatches: list[tuple[str, str, Event]] = []
        self.call_count = 0

    async def complete(self, prompt: PromptInput) -> ModelOutput:
        self.call_count += 1
        return ModelOutput(content="recorded")


class MockEventStore(EventStoreProtocol):
    appended: list[Event] = []

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


def _make_event(event_type: str | EventType, project_id: str = "proj-1", payload: dict[str, Any] = {}) -> Event:
    return Event(
        event_id="evt-1",
        project_id=project_id,
        event_type=str(event_type),
        participant_id="user-1",
        participant_type="human",
        participant_display_name="Test",
        payload=payload,
        correlation_id="corr-1",
        created_at=datetime.now(UTC),
    )


@pytest.fixture
async def event_bus() -> InProcessEventBus:
    return InProcessEventBus()


@pytest.fixture
async def mock_adapter() -> DispatchRecorder:
    return DispatchRecorder()


@pytest.fixture
async def mock_store() -> MockEventStore:
    return MockEventStore()


@pytest.fixture
async def runtime(
    mock_adapter: DispatchRecorder, mock_store: MockEventStore, event_bus: InProcessEventBus
) -> AgentRuntime:
    return AgentRuntime(event_bus, mock_store, mock_adapter)


@pytest.fixture
async def scheduler(event_bus: InProcessEventBus, runtime: AgentRuntime) -> AgentScheduler:
    return AgentScheduler(event_bus, runtime)


# -- TC-12.2: SummaryAgent→DiscussionMessageCreated调度 --


async def test_tc12_2_summary_dispatch(
    event_bus: InProcessEventBus, runtime: AgentRuntime, scheduler: AgentScheduler, mock_adapter: DispatchRecorder
) -> None:
    """TC-12.2: DiscussionMessageCreated(request_summary=true)→dispatch summary"""
    runtime.register("proj-1", SUMMARY_DECLARATION)
    event = _make_event(
        EventType.DiscussionMessageCreated, "proj-1", {"thread_id": "t1", "content": "hello", "request_summary": True}
    )
    await event_bus.publish(event)
    await event_bus.wait_for_pending()
    assert mock_adapter.call_count >= 1


# -- TC-12.3: DecomposeAgent→DiscussionSummaryGenerated调度 --


async def test_tc12_3_decompose_dispatch(
    event_bus: InProcessEventBus, runtime: AgentRuntime, scheduler: AgentScheduler, mock_adapter: DispatchRecorder
) -> None:
    """TC-12.3: DiscussionSummaryGenerated→dispatch decompose"""
    runtime.register("proj-1", DECOMPOSE_DECLARATION)
    event = _make_event(
        EventType.DiscussionSummaryGenerated,
        "proj-1",
        {
            "thread_id": "t1",
            "summary_id": "s1",
            "consensus_points": [],
            "divergence_points": [],
            "action_items": [],
            "knowledge_references": [],
        },
    )
    await event_bus.publish(event)
    await event_bus.wait_for_pending()
    assert mock_adapter.call_count >= 1


# -- TC-12.4: ExecuteAgent→ExecutionPlanApproved调度 --


async def test_tc12_4_execute_plan_approved(
    event_bus: InProcessEventBus, runtime: AgentRuntime, scheduler: AgentScheduler, mock_adapter: DispatchRecorder
) -> None:
    """TC-12.4: ExecutionPlanApproved→dispatch execute"""
    runtime.register("proj-1", EXECUTE_DECLARATION)
    event = _make_event(EventType.ExecutionPlanApproved, "proj-1", {"plan_id": "p1", "approved_tasks": ["task1"]})
    await event_bus.publish(event)
    await event_bus.wait_for_pending()
    assert mock_adapter.call_count >= 1


# -- TC-12.5: ExecuteAgent→TaskOutputRevisionRequested调度 --


async def test_tc12_5_execute_revision_requested(
    event_bus: InProcessEventBus, runtime: AgentRuntime, scheduler: AgentScheduler, mock_adapter: DispatchRecorder
) -> None:
    """TC-12.5: TaskOutputRevisionRequested→dispatch execute"""
    runtime.register("proj-1", EXECUTE_DECLARATION)
    event = _make_event(
        EventType.TaskOutputRevisionRequested,
        "proj-1",
        {"output_id": "o1", "task_id": "task1", "issues": ["i1"], "suggestions": ["s1"]},
    )
    await event_bus.publish(event)
    await event_bus.wait_for_pending()
    assert mock_adapter.call_count >= 1


# -- TC-12.10: Summary Agent阈值触发 --


async def test_tc12_10_threshold_trigger(
    event_bus: InProcessEventBus, runtime: AgentRuntime, scheduler: AgentScheduler, mock_adapter: DispatchRecorder
) -> None:
    """TC-12.10: 10条消息(request_summary=false)→第10条触发summary Agent"""
    runtime.register("proj-1", SUMMARY_DECLARATION)

    # 发送9条request_summary=false的消息→不触发
    for i in range(9):
        event = _make_event(
            EventType.DiscussionMessageCreated,
            "proj-1",
            {"thread_id": "t-threshold", "content": f"msg-{i}", "request_summary": False},
        )
        await event_bus.publish(event)
        await event_bus.wait_for_pending()
    assert mock_adapter.call_count == 0

    # 第10条消息→触发（阈值=10）
    event10 = _make_event(
        EventType.DiscussionMessageCreated,
        "proj-1",
        {"thread_id": "t-threshold", "content": "msg-10", "request_summary": False},
    )
    await event_bus.publish(event10)
    await event_bus.wait_for_pending()
    assert mock_adapter.call_count >= 1


async def test_tc12_10_request_summary_immediate(
    event_bus: InProcessEventBus, runtime: AgentRuntime, scheduler: AgentScheduler, mock_adapter: DispatchRecorder
) -> None:
    """TC-12.10补充: request_summary=true立即触发（不等待阈值）"""
    runtime.register("proj-1", SUMMARY_DECLARATION)

    # 只发1条request_summary=true的消息→立即触发
    event = _make_event(
        EventType.DiscussionMessageCreated,
        "proj-1",
        {"thread_id": "t-immediate", "content": "important!", "request_summary": True},
    )
    await event_bus.publish(event)
    await event_bus.wait_for_pending()
    assert mock_adapter.call_count >= 1
