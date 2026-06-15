"""SSE流端点路由——GET /events/stream"""

import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sse_starlette.sse import EventSourceResponse

from app.biz.projects.read_repo import ProjectReadProtocol
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


async def _check_project_member(
    request: Request,
    project_id: str = Query(...),
    user: User = Depends(_get_sse_user),
) -> User:
    """认证+项目成员授权：非成员无法订阅项目事件流"""
    project_read: ProjectReadProtocol = cast(ProjectReadProtocol, request.app.state.project_read)
    if not await project_read.check_member_exists(project_id, user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a project member")
    return user


@router.get("/stream")
async def event_stream(
    request: Request,
    project_id: str = Query(...),
    user: User = Depends(_check_project_member),
) -> EventSourceResponse:
    """SSE事件流端点：按project_id推送Orbion事件（仅项目成员可订阅）"""
    sse_channel: SSEChannel = request.app.state.sse_channel

    async def generate() -> AsyncGenerator[dict[str, Any], None]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        sse_channel.add_connection(project_id, queue)
        yield {"event": "connected", "data": json.dumps({"project_id": project_id})}
        try:
            while True:
                sse_event = await queue.get()
                yield sse_event
        finally:
            sse_channel.remove_connection(project_id, queue)

    return EventSourceResponse(generate(), ping=15)
