"""认证API端点：注册、登录、审批"""

import uuid
from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Request

from app.config import Settings, get_settings
from app.hub.auth.dependencies import require_admin_dependency
from app.hub.auth.models import (
    ApprovalResponse,
    PendingUserResponse,
    RegistrationResponse,
    RejectionRequest,
    User,
    UserLogin,
    UserRegister,
    UserResponse,
)
from app.hub.auth.policy import AdminApprovalPolicy
from app.hub.auth.repository import UserRepositoryProvider
from app.hub.auth.service import create_access_token, hash_password, verify_password
from app.hub.events.bus import EventBus
from app.hub.events.store import EventStoreProtocol
from app.hub.events.types import Event, EventType, UserRegisteredPayload

router = APIRouter()


# -- FastAPI依赖：从app.state获取共享基础设施 --


async def _get_user_repo_provider(request: Request) -> UserRepositoryProvider:
    """从app.state获取UserRepositoryProvider（singleton，self-managed pool）"""
    return cast(UserRepositoryProvider, request.app.state.user_repo_provider)


async def _get_event_store(request: Request) -> EventStoreProtocol:
    return cast(EventStoreProtocol, request.app.state.event_store)


async def _get_event_bus(request: Request) -> EventBus:
    return cast(EventBus, request.app.state.event_bus)


@router.post("/register", response_model=RegistrationResponse)
async def register(
    request: UserRegister,
    provider: UserRepositoryProvider = Depends(_get_user_repo_provider),
    settings: Settings = Depends(get_settings),
    event_store: EventStoreProtocol = Depends(_get_event_store),
    event_bus: EventBus = Depends(_get_event_bus),
) -> RegistrationResponse:
    """用户注册：首个用户自动审批+is_admin，后续用户pending"""
    # async with repo 内的 HTTPException 会触发事务 rollback；
    # 当前所有端点均在写入前抛出异常（纯读校验），故 rollback 无副作用
    async with provider.scoped() as repo:
        if await repo.check_username_exists(request.username):
            raise HTTPException(status_code=409, detail="Username already exists")

        policy = AdminApprovalPolicy()
        decision = await policy.evaluate(request, repo)

        password_hash = hash_password(request.password)
        user_record = await repo.create_user(
            request.username,
            password_hash,
            request.display_name,
            decision.status,
            decision.is_admin,
        )
        user_id = user_record.id
        user_status = user_record.status

    # 事务提交后写事件（EventStore使用独立连接池）
    event_payload = UserRegisteredPayload(
        username=request.username,
        display_name=request.display_name,
        status=decision.status,
        is_admin=decision.is_admin,
    )
    event = Event(
        event_id=str(uuid.uuid4()),
        project_id="",  # 平台级事件
        event_type=EventType.UserRegistered,
        participant_id=user_id,
        participant_type="human",
        participant_display_name=request.display_name,
        payload=event_payload.model_dump(mode="json"),
        correlation_id=user_id,
    )
    await event_store.append(event)
    await event_bus.publish(event)

    if user_status == "active":
        token = create_access_token(
            user_id=user_id,
            username=request.username,
            display_name=request.display_name,
            is_admin=decision.is_admin,
            settings=settings,
        )
        return RegistrationResponse(
            user_id=user_id,
            username=request.username,
            display_name=request.display_name,
            status="active",
            access_token=token,
            token_type="bearer",
            message=decision.message,
        )
    return RegistrationResponse(
        user_id=user_id,
        username=request.username,
        display_name=request.display_name,
        status="pending",
        message=decision.message,
    )


@router.post("/login", response_model=UserResponse)
async def login(
    request: UserLogin,
    provider: UserRepositoryProvider = Depends(_get_user_repo_provider),
    settings: Settings = Depends(get_settings),
) -> UserResponse:
    """用户登录：pending/rejected返回403，密码错误返回401"""
    async with provider.scoped() as repo:
        user_record = await repo.get_user_by_username(request.username)
        if user_record is None:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        if user_record.status == "pending":
            raise HTTPException(status_code=403, detail="Account pending admin approval")
        if user_record.status == "rejected":
            raise HTTPException(status_code=403, detail="Account registration was rejected")

        if not verify_password(request.password, user_record.password_hash):
            raise HTTPException(status_code=401, detail="Invalid credentials")

        token = create_access_token(
            user_id=user_record.id,
            username=user_record.username,
            display_name=user_record.display_name,
            is_admin=user_record.is_admin,
            settings=settings,
        )
        return UserResponse(
            user_id=user_record.id,
            username=user_record.username,
            display_name=user_record.display_name,
            access_token=token,
        )


@router.get("/users/pending", response_model=list[PendingUserResponse])
async def list_pending(
    admin: User = Depends(require_admin_dependency),
    provider: UserRepositoryProvider = Depends(_get_user_repo_provider),
) -> list[PendingUserResponse]:
    """列出待审批用户，仅is_admin可访问"""
    # read-only操作也使用事务模式，保持与写端点的repo使用模式一致
    async with provider.scoped() as repo:
        rows = await repo.list_pending_users()
        return [
            PendingUserResponse(
                user_id=r.id,
                username=r.username,
                display_name=r.display_name,
                status=r.status,
                created_at=r.created_at,
            )
            for r in rows
        ]


@router.post("/users/{user_id}/approve", response_model=ApprovalResponse)
async def approve_user(
    user_id: str,
    admin: User = Depends(require_admin_dependency),
    provider: UserRepositoryProvider = Depends(_get_user_repo_provider),
) -> ApprovalResponse:
    """管理员审批用户：pending→active"""
    async with provider.scoped() as repo:
        user_record = await repo.get_user_by_id(user_id)
        if user_record is None:
            raise HTTPException(status_code=404, detail="User not found")
        if user_record.status == "active":
            raise HTTPException(status_code=400, detail="User is already active")
        if user_record.status == "rejected":
            raise HTTPException(status_code=400, detail="User was already rejected")

        await repo.update_user_status(user_id, "active")

        return ApprovalResponse(
            user_id=user_id,
            username=user_record.username,
            display_name=user_record.display_name,
            status="active",
        )


@router.post("/users/{user_id}/reject", response_model=ApprovalResponse)
async def reject_user(
    user_id: str,
    body: RejectionRequest | None = None,
    admin: User = Depends(require_admin_dependency),
    provider: UserRepositoryProvider = Depends(_get_user_repo_provider),
) -> ApprovalResponse:
    """管理员拒绝用户：pending→rejected"""
    async with provider.scoped() as repo:
        user_record = await repo.get_user_by_id(user_id)
        if user_record is None:
            raise HTTPException(status_code=404, detail="User not found")
        if user_record.status == "active":
            raise HTTPException(status_code=400, detail="User is already active")
        if user_record.status == "rejected":
            raise HTTPException(status_code=400, detail="User was already rejected")

        await repo.update_user_status(user_id, "rejected")

        reason = body.reason if body else None
        return ApprovalResponse(
            user_id=user_id,
            username=user_record.username,
            display_name=user_record.display_name,
            status="rejected",
            reason=reason,
        )
