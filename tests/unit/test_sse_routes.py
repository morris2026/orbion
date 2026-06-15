"""SSE路由单元测试：验证keepalive参数和generator行为"""

import asyncio
import json
from typing import Any
from unittest.mock import MagicMock

from sse_starlette.sse import EventSourceResponse

from app.hub.channels.routes import event_stream
from app.hub.channels.sse import SSEChannel
from app.hub.events.bus import InProcessEventBus


async def test_event_stream_keepalive_ping_interval() -> None:
    """event_stream应配置ping_interval=15，由框架发送keepalive注释防止连接被中间件超时断开"""
    mock_request = MagicMock()
    mock_request.app.state.sse_channel = MagicMock()
    mock_user = MagicMock()

    response = await event_stream(request=mock_request, project_id="test-proj", user=mock_user)

    assert isinstance(response, EventSourceResponse)
    assert response.ping_interval == 15


async def test_generator_yields_connected_then_events() -> None:
    """generate()应先yield connected事件，再yield队列中的业务事件"""
    event_bus = InProcessEventBus()
    sse_channel = SSEChannel(event_bus)
    mock_request = MagicMock()
    mock_request.app.state.sse_channel = sse_channel
    mock_user = MagicMock()

    response = await event_stream(request=mock_request, project_id="proj-1", user=mock_user)

    received: list[dict[str, Any]] = []

    async def consume() -> None:
        async for event in response.body_iterator:
            if isinstance(event, dict):
                received.append(event)

    task = asyncio.create_task(consume())
    # 等待 connected 事件被消费
    await asyncio.sleep(0.05)

    # 推送一个业务事件到 SSEChannel
    await sse_channel.send_event("proj-1", "test_event", {"key": "value"})
    # 等待业务事件被消费
    await asyncio.sleep(0.05)

    # 取消 task（queue.get() 无限等待，只能通过取消退出）
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert len(received) >= 2
    assert received[0]["event"] == "connected"
    assert json.loads(received[0]["data"])["project_id"] == "proj-1"
    assert received[1]["event"] == "test_event"


async def test_generator_cleanup_on_disconnect() -> None:
    """generator被取消（模拟客户端断开）时应调用remove_connection清理连接，且空project_id条目被删除"""
    event_bus = InProcessEventBus()
    sse_channel = SSEChannel(event_bus)
    mock_request = MagicMock()
    mock_request.app.state.sse_channel = sse_channel
    mock_user = MagicMock()

    response = await event_stream(request=mock_request, project_id="proj-1", user=mock_user)

    async def consume() -> None:
        async for _ in response.body_iterator:
            pass

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.05)

    # 验证连接已注册
    assert "proj-1" in sse_channel._connections
    assert len(sse_channel._connections["proj-1"]) == 1

    # 模拟客户端断开
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    # 验证连接已清理
    assert "proj-1" not in sse_channel._connections
