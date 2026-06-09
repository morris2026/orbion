"""AgentRuntime状态机UT：MVP-12.6、MVP-12.7、MVP-12.11"""

from datetime import UTC, datetime

from app.biz.agents.adapters.base import ModelOutput, PromptInput
from app.biz.agents.declarations import SUMMARY_DECLARATION
from app.biz.agents.runtime import AgentRuntime
from app.hub.events.bus import InProcessEventBus
from app.hub.events.store import EventStoreProtocol
from app.hub.events.types import Event


class MockModelAdapter:
    """可控的mock adapter——成功或失败"""

    def __init__(self, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.call_count = 0

    async def complete(self, prompt: PromptInput) -> ModelOutput:
        self.call_count += 1
        if self.should_fail:
            raise RuntimeError("Mock adapter failure")
        return ModelOutput(content="mock output")


class MockEventStore(EventStoreProtocol):
    """mock EventStore——记录append但不写DB"""

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


def _make_event(project_id: str = "proj-1") -> Event:
    return Event(
        event_id="evt-1",
        project_id=project_id,
        event_type="DiscussionMessageCreated",
        participant_id="user-1",
        participant_type="human",
        participant_display_name="Test",
        payload={"thread_id": "t1", "content": "hello", "request_summary": True},
        correlation_id="corr-1",
        created_at=datetime.now(UTC),
    )


# -- MVP-12.6: idle→running→idle --


async def test_tc12_6_idle_running_idle() -> None:
    """MVP-12.6: dispatch→running→产出完成→回到idle"""
    bus = InProcessEventBus()
    store = MockEventStore()
    adapter = MockModelAdapter(should_fail=False)
    runtime = AgentRuntime(bus, store, adapter)

    runtime.register("proj-1", SUMMARY_DECLARATION)
    event = _make_event("proj-1")

    await runtime.dispatch("proj-1", "summary", event)

    state = runtime._agents["proj-1"]["summary"]
    assert state.status == "idle"
    assert state.completed_count == 1
    assert state.current_task is None
    assert adapter.call_count == 1


# -- MVP-12.7: idle→running→error --


async def test_tc12_7_idle_running_error() -> None:
    """MVP-12.7: dispatch→running→执行失败→error"""
    bus = InProcessEventBus()
    store = MockEventStore()
    adapter = MockModelAdapter(should_fail=True)
    runtime = AgentRuntime(bus, store, adapter)

    runtime.register("proj-1", SUMMARY_DECLARATION)
    event = _make_event("proj-1")

    await runtime.dispatch("proj-1", "summary", event)

    state = runtime._agents["proj-1"]["summary"]
    assert state.status == "error"
    assert state.error_count == 1
    assert state.last_error == "Mock adapter failure"
    assert state.current_task is None


# -- MVP-12.11: Agent不并发执行 --


async def test_tc12_11_no_concurrent_execution() -> None:
    """MVP-12.11: Agent处于running时不接受新任务；回到idle后可再次dispatch

    dispatch是同步await调用，用create_task并发测试在pytest-asyncio函数级loop中会死锁。
    正确方案：直接设置running状态→dispatch被拒绝→恢复idle→dispatch成功。
    """
    bus = InProcessEventBus()
    store = MockEventStore()
    adapter = MockModelAdapter(should_fail=False)
    runtime = AgentRuntime(bus, store, adapter)
    runtime.register("proj-1", SUMMARY_DECLARATION)
    state = runtime._agents["proj-1"]["summary"]

    event1 = _make_event("proj-1")
    event2 = _make_event("proj-1")
    event2.event_id = "evt-2"

    # 手动设置为running（模拟第一次dispatch正在执行）
    state.status = "running"
    state.current_task = event1.event_id

    # running状态下dispatch→被拒绝（不调用adapter）
    await runtime.dispatch("proj-1", "summary", event2)
    assert adapter.call_count == 0
    assert state.status == "running"

    # 模拟第一次dispatch完成→恢复idle
    state.status = "idle"
    state.current_task = None

    # idle后再次dispatch→成功
    await runtime.dispatch("proj-1", "summary", event2)
    assert adapter.call_count == 1
    assert state.status == "idle"
    assert state.completed_count == 1
