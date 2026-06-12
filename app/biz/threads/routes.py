"""讨论线程与消息API端点"""

from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Request

from app.biz.threads.models import MessageCreate, MessageResponse, ThreadCreate, ThreadListItem, ThreadResponse
from app.biz.threads.service import ThreadService
from app.hub.auth.dependencies import get_current_user
from app.hub.auth.models import User

# 线程端点路由（prefix由main.py注册时指定）
thread_router = APIRouter()

# 消息端点路由（prefix由main.py注册时指定）
message_router = APIRouter()


async def _get_thread_service(request: Request) -> ThreadService:
    return cast(ThreadService, request.app.state.thread_service)


# -- 线程端点 --


@thread_router.post("", response_model=ThreadResponse)
async def create_thread(
    project_id: str,
    request: ThreadCreate,
    user: User = Depends(get_current_user),
    service: ThreadService = Depends(_get_thread_service),
) -> ThreadResponse:
    """创建线程，项目成员可操作"""
    # 权限检查：项目成员才能创建线程
    if not await service.check_member_exists(project_id, user.id):
        raise HTTPException(status_code=403, detail="Not a project member")
    try:
        thread = await service.create_thread(project_id, request.title, request.type, user)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return ThreadResponse(**thread)


@thread_router.get("", response_model=list[ThreadListItem])
async def list_threads(
    project_id: str,
    user: User = Depends(get_current_user),
    service: ThreadService = Depends(_get_thread_service),
) -> list[ThreadListItem]:
    """线程列表含聚合字段，项目成员可查看"""
    # 权限检查
    if not await service.check_member_exists(project_id, user.id):
        raise HTTPException(status_code=403, detail="Not a project member")
    threads = await service.list_threads(project_id)
    return [ThreadListItem(**t) for t in threads]


@thread_router.delete("/{thread_id}")
async def delete_thread(
    project_id: str,
    thread_id: str,
    user: User = Depends(get_current_user),
    service: ThreadService = Depends(_get_thread_service),
) -> dict[str, str]:
    """删除线程，需要DELETE_PROJECT权限，不允许删除默认线程"""
    try:
        success = await service.delete_thread(project_id, thread_id, user.id)
    except PermissionError:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not success:
        raise HTTPException(status_code=403, detail="Not a project member")
    return {"status": "deleted"}


# -- 消息端点 --


@message_router.post("", response_model=MessageResponse)
async def send_message(
    thread_id: str,
    request: MessageCreate,
    user: User = Depends(get_current_user),
    service: ThreadService = Depends(_get_thread_service),
) -> MessageResponse:
    """发送消息，项目成员可操作"""
    # 获取thread的project_id
    project_id = await service.get_thread_project_id(thread_id)
    if project_id is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    # 权限检查：项目成员才能发送消息
    if not await service.check_member_exists(project_id, user.id):
        raise HTTPException(status_code=403, detail="Not a project member")

    try:
        msg = await service.send_message(thread_id, request.content, request.request_summary, user)
    except ValueError as e:
        if "not found" in str(e):
            raise HTTPException(status_code=404, detail="Thread not found")
        raise
    return MessageResponse(**msg)


@message_router.get("", response_model=list[MessageResponse])
async def list_messages(
    thread_id: str,
    before: str | None = None,
    limit: int = 50,
    user: User = Depends(get_current_user),
    service: ThreadService = Depends(_get_thread_service),
) -> list[MessageResponse]:
    """消息列表游标分页，项目成员可查看"""
    # 获取thread的project_id
    project_id = await service.get_thread_project_id(thread_id)
    if project_id is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    # 权限检查
    if not await service.check_member_exists(project_id, user.id):
        raise HTTPException(status_code=403, detail="Not a project member")

    messages = await service.list_messages(thread_id, before, limit)
    return [MessageResponse(**m) for m in messages]
