"""MVP-3.1–MVP-3.6: EventBus抽象接口与进程内实现"""

import asyncio
import time
from typing import Never

from app.hub.events.bus import EventBus, InProcessEventBus
from app.hub.events.types import Event


class TestEventBusPublishSubscribe:
    """MVP-3.1: publish后subscribe的handler收到Event"""

    async def test_handler_receives_event(self) -> None:
        bus = InProcessEventBus()
        received: list[Event] = []

        async def handler(event: Event) -> None:
            received.append(event)

        bus.subscribe("TestEvent", handler)
        event = Event(
            event_id="evt-1",
            project_id="proj-1",
            event_type="TestEvent",
            participant_id="user-1",
            participant_type="human",
            payload={"data": "hello"},
            correlation_id="corr-1",
        )
        await bus.publish(event)

        await asyncio.sleep(0.1)
        assert len(received) == 1
        assert received[0] == event


class TestEventBusUnsubscribe:
    """MVP-3.2: unsubscribe后不再收到事件"""

    async def test_unsubscribe_stops_delivery(self) -> None:
        bus = InProcessEventBus()
        received: list[Event] = []

        async def handler(event: Event) -> None:
            received.append(event)

        sub_id = bus.subscribe("TestEvent", handler)
        bus.unsubscribe(sub_id)
        event = Event(
            event_id="evt-2",
            project_id="proj-1",
            event_type="TestEvent",
            participant_id="user-1",
            participant_type="human",
            payload={"data": "ignored"},
            correlation_id="corr-2",
        )
        await bus.publish(event)

        await asyncio.sleep(0.1)
        assert len(received) == 0


class TestEventBusMultipleHandlers:
    """MVP-3.3: 多handler订阅同一事件类型"""

    async def test_all_handlers_receive_event(self) -> None:
        bus = InProcessEventBus()
        received1: list[Event] = []
        received2: list[Event] = []

        async def handler1(event: Event) -> None:
            received1.append(event)

        async def handler2(event: Event) -> None:
            received2.append(event)

        bus.subscribe("TestEvent", handler1)
        bus.subscribe("TestEvent", handler2)
        event = Event(
            event_id="evt-3",
            project_id="proj-1",
            event_type="TestEvent",
            participant_id="user-1",
            participant_type="human",
            payload={"data": "shared"},
            correlation_id="corr-3",
        )
        await bus.publish(event)

        await asyncio.sleep(0.1)
        assert len(received1) == 1
        assert received1[0] == event
        assert len(received2) == 1
        assert received2[0] == event


class TestEventBusHandlerException:
    """MVP-3.4: handler异常不阻塞publish和其他handler"""

    async def test_bad_handler_does_not_block_publish_or_good_handler(self) -> None:
        bus = InProcessEventBus()
        received: list[Event] = []

        async def bad_handler(event: Event) -> Never:
            raise RuntimeError("handler failed")

        async def good_handler(event: Event) -> None:
            received.append(event)

        bus.subscribe("TestEvent", bad_handler)
        bus.subscribe("TestEvent", good_handler)
        event = Event(
            event_id="evt-4",
            project_id="proj-1",
            event_type="TestEvent",
            participant_id="user-1",
            participant_type="human",
            payload={"data": "test"},
            correlation_id="corr-4",
        )
        await bus.publish(event)

        await asyncio.sleep(0.1)
        assert len(received) == 1
        assert received[0] == event


class TestEventBusUnsubscribedEventType:
    """MVP-3.5: 未订阅的事件类型publish无异常"""

    async def test_publish_unknown_event_type_no_exception(self) -> None:
        bus = InProcessEventBus()
        event = Event(
            event_id="evt-5",
            project_id="proj-1",
            event_type="UnknownEvent",
            participant_id="user-1",
            participant_type="human",
            payload={"data": "nothing"},
            correlation_id="corr-5",
        )
        await bus.publish(event)
        # 无异常、无handler被调用 — 测试就是成功


class TestEventBusAsyncNonBlocking:
    """MVP-3.6: handler异步不阻塞publish"""

    async def test_slow_handler_does_not_block_publish(self) -> None:
        bus = InProcessEventBus()

        async def slow_handler(event: Event) -> None:
            await asyncio.sleep(1.0)

        bus.subscribe("TestEvent", slow_handler)
        event = Event(
            event_id="evt-6",
            project_id="proj-1",
            event_type="TestEvent",
            participant_id="user-1",
            participant_type="human",
            payload={"data": "fast"},
            correlation_id="corr-6",
        )

        start = time.monotonic()
        await bus.publish(event)
        elapsed = time.monotonic() - start

        assert elapsed < 0.5  # publish应立即返回，不等handler完成


class TestEventBusProtocolConformance:
    """InProcessEventBus符合EventBus Protocol"""

    def test_inprocess_event_bus_satisfies_protocol(self) -> None:
        bus = InProcessEventBus()
        assert isinstance(bus, EventBus)
