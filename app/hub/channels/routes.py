"""SSE流端点路由——GET /events/stream（用户级连接）"""

import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sse_starlette.sse import EventSourceResponse

from app.config import Settings, get_settings
from app.hub.auth.dependencies import get_current_user_from_token
from app.hub.auth.models import User
from app.hub.channels.sse import SSEChannel

router = APIRouter()


async def _get_sse_user(
    request: Request,
    token: str | None = Query(None),
    settings: Settings = Depends(get_settings),
) -> User:
    """SSE认证：支持query param token和Authorization header（EventSource不支持自定义header）"""
    if token:
        return get_current_user_from_token(token, settings)
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return get_current_user_from_token(auth_header[7:], settings)
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")


@router.get("/stream")
async def event_stream(
    request: Request,
    user: User = Depends(_get_sse_user),
) -> EventSourceResponse:
    """SSE事件流端点：用户级连接，推送该用户所有项目的事件"""
    sse_channel: SSEChannel = request.app.state.sse_channel

    async def generate() -> AsyncGenerator[dict[str, Any], None]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        await sse_channel.add_connection(user.id, queue)
        yield {"event": "connected", "data": json.dumps({"user_id": user.id})}
        try:
            while True:
                sse_event = await queue.get()
                yield sse_event
        finally:
            sse_channel.remove_connection(user.id, queue)

    return EventSourceResponse(generate(), ping=15)
