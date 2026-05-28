"""EventBus Protocol与InProcessEventBus实现"""

import asyncio
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4

logger = logging.getLogger(__name__)

Handler = Callable[[dict[str, Any]], Awaitable[None]]


@runtime_checkable
class EventBus(Protocol):
    """事件发布/订阅抽象接口"""

    async def publish(self, event_type: str, payload: dict[str, Any]) -> None: ...
    def subscribe(
        self,
        event_type: str,
        handler: Handler,
    ) -> str: ...
    def unsubscribe(self, subscription_id: str) -> None: ...


async def _safe_run(handler: Handler, payload: dict[str, Any]) -> None:
    try:
        await handler(payload)
    except Exception:
        logger.exception("EventBus handler error")


class InProcessEventBus:
    """进程内事件总线，asyncio.create_task调度handler"""

    def __init__(self) -> None:
        self._handlers: dict[str, list[tuple[str, Handler]]] = defaultdict(list)

    async def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        handlers = self._handlers.get(event_type, [])
        for _sub_id, handler in handlers:
            asyncio.create_task(_safe_run(handler, payload))

    def subscribe(
        self,
        event_type: str,
        handler: Handler,
    ) -> str:
        sub_id = uuid4().hex
        self._handlers[event_type].append((sub_id, handler))
        return sub_id

    def unsubscribe(self, subscription_id: str) -> None:
        for event_type, subscribers in self._handlers.items():
            self._handlers[event_type] = [(sid, h) for sid, h in subscribers if sid != subscription_id]
