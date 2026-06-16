"""ThreadService.send_system_message 测试"""

import asyncio
import uuid
from unittest.mock import AsyncMock

import pytest

from app.biz.threads.service import ThreadService
from app.hub.events.bus import InProcessEventBus
from app.hub.events.types import Event, EventType


def _make_thread_service() -> tuple[ThreadService, AsyncMock, InProcessEventBus]:
    event_store = AsyncMock()
    event_bus = InProcessEventBus()
    thread_read = AsyncMock()
    project_read = AsyncMock()
    service = ThreadService(event_store, event_bus, thread_read, project_read)
    return service, event_store, event_bus


class TestSendSystemMessage:
    """send_system_message：以 system 身份发送 DiscussionMessageCreated 事件"""

    @pytest.mark.asyncio
    async def test_sends_event_with_system_participant(self) -> None:
        service, event_store, event_bus = _make_thread_service()
        project_id = str(uuid.uuid4())
        thread_id = str(uuid.uuid4())

        await service.send_system_message(project_id, thread_id, "仓库 test 已克隆")

        event_store.append.assert_awaited_once()
        event = event_store.append.call_args[0][0]
        assert event.event_type == EventType.DiscussionMessageCreated
        assert event.participant_type == "system"
        assert event.participant_id == "system"
        assert event.participant_display_name == "系统"
        assert event.payload["content"] == "仓库 test 已克隆"
        assert event.payload["thread_id"] == thread_id
        assert event.project_id == project_id

    @pytest.mark.asyncio
    async def test_publishes_event_to_bus(self) -> None:
        service, event_store, event_bus = _make_thread_service()
        received_events: list[Event] = []

        async def handler(event: Event) -> None:
            received_events.append(event)

        event_bus.subscribe(EventType.DiscussionMessageCreated, handler)
        project_id = str(uuid.uuid4())
        thread_id = str(uuid.uuid4())

        await service.send_system_message(project_id, thread_id, "测试消息")
        # EventBus.publish 用 create_task 分发，需要让出控制权
        await asyncio.sleep(0)

        assert len(received_events) == 1
        assert received_events[0].participant_type == "system"
