"""TC-3.1–TC-3.6: EventBus抽象接口与进程内实现"""

import asyncio
import time
from typing import Any, Never

from app.hub.events.bus import EventBus, InProcessEventBus


class TestEventBusPublishSubscribe:
    """TC-3.1: publish后subscribe的handler收到payload"""

    async def test_handler_receives_payload(self) -> None:
        bus = InProcessEventBus()
        received: list[dict[str, Any]] = []

        async def handler(payload: dict[str, Any]) -> None:
            received.append(payload)

        bus.subscribe("TestEvent", handler)
        payload = {"project_id": "proj-1", "data": "hello"}
        await bus.publish("TestEvent", payload)

        await asyncio.sleep(0.1)
        assert len(received) == 1
        assert received[0] == payload


class TestEventBusUnsubscribe:
    """TC-3.2: unsubscribe后不再收到事件"""

    async def test_unsubscribe_stops_delivery(self) -> None:
        bus = InProcessEventBus()
        received: list[dict[str, Any]] = []

        async def handler(payload: dict[str, Any]) -> None:
            received.append(payload)

        sub_id = bus.subscribe("TestEvent", handler)
        bus.unsubscribe(sub_id)
        await bus.publish("TestEvent", {"data": "ignored"})

        await asyncio.sleep(0.1)
        assert len(received) == 0


class TestEventBusMultipleHandlers:
    """TC-3.3: 多handler订阅同一事件类型"""

    async def test_all_handlers_receive_payload(self) -> None:
        bus = InProcessEventBus()
        received1: list[dict[str, Any]] = []
        received2: list[dict[str, Any]] = []

        async def handler1(payload: dict[str, Any]) -> None:
            received1.append(payload)

        async def handler2(payload: dict[str, Any]) -> None:
            received2.append(payload)

        bus.subscribe("TestEvent", handler1)
        bus.subscribe("TestEvent", handler2)
        payload = {"project_id": "proj-1", "data": "shared"}
        await bus.publish("TestEvent", payload)

        await asyncio.sleep(0.1)
        assert len(received1) == 1
        assert received1[0] == payload
        assert len(received2) == 1
        assert received2[0] == payload


class TestEventBusHandlerException:
    """TC-3.4: handler异常不阻塞publish和其他handler"""

    async def test_bad_handler_does_not_block_publish_or_good_handler(self) -> None:
        bus = InProcessEventBus()
        received: list[dict[str, Any]] = []

        async def bad_handler(payload: dict[str, Any]) -> Never:
            raise RuntimeError("handler failed")

        async def good_handler(payload: dict[str, Any]) -> None:
            received.append(payload)

        bus.subscribe("TestEvent", bad_handler)
        bus.subscribe("TestEvent", good_handler)
        payload = {"project_id": "proj-1", "data": "test"}
        await bus.publish("TestEvent", payload)

        await asyncio.sleep(0.1)
        assert len(received) == 1
        assert received[0] == payload


class TestEventBusUnsubscribedEventType:
    """TC-3.5: 未订阅的事件类型publish无异常"""

    async def test_publish_unknown_event_type_no_exception(self) -> None:
        bus = InProcessEventBus()
        await bus.publish("UnknownEvent", {"data": "nothing"})
        # 无异常、无handler被调用 — 测试就是成功


class TestEventBusAsyncNonBlocking:
    """TC-3.6: handler异步不阻塞publish"""

    async def test_slow_handler_does_not_block_publish(self) -> None:
        bus = InProcessEventBus()

        async def slow_handler(payload: dict[str, Any]) -> None:
            await asyncio.sleep(1.0)

        bus.subscribe("TestEvent", slow_handler)

        start = time.monotonic()
        await bus.publish("TestEvent", {"data": "fast"})
        elapsed = time.monotonic() - start

        assert elapsed < 0.5  # publish应立即返回，不等handler完成


class TestEventBusProtocolConformance:
    """InProcessEventBus符合EventBus Protocol"""

    def test_inprocess_event_bus_satisfies_protocol(self) -> None:
        bus = InProcessEventBus()
        assert isinstance(bus, EventBus)
