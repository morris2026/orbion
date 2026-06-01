"""认证API端点：注册、登录、审批"""

import uuid
from typing import cast

import asyncpg
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
from app.hub.auth.service import (
    check_username_exists,
    create_access_token,
    create_user,
    get_user_by_id,
    get_user_by_username,
    hash_password,
    list_pending_users,
    update_user_status,
    verify_password,
)
from app.hub.events.bus import EventBus
from app.hub.events.store import EventStoreProtocol
from app.hub.events.types import Event, EventType, UserRegisteredPayload

router = APIRouter()


# -- FastAPI依赖：从app.state获取共享基础设施 --


async def _get_pool(request: Request) -> asyncpg.Pool:
    """从app.state获取共享连接池"""
    return cast("asyncpg.Pool", request.app.state.pool)


async def _get_event_store(request: Request) -> EventStoreProtocol:
    return cast(EventStoreProtocol, request.app.state.event_store)


async def _get_event_bus(request: Request) -> EventBus:
    return cast(EventBus, request.app.state.event_bus)


@router.post("/register", response_model=RegistrationResponse)
async def register(
    request: UserRegister,
    pool: asyncpg.Pool = Depends(_get_pool),
    settings: Settings = Depends(get_settings),
    event_store: EventStoreProtocol = Depends(_get_event_store),
    event_bus: EventBus = Depends(_get_event_bus),
) -> RegistrationResponse:
    """用户注册：首个用户自动审批+is_admin，后续用户pending"""
    async with pool.acquire() as conn:
        async with conn.transaction():
            if await check_username_exists(conn, request.username):
                raise HTTPException(status_code=409, detail="Username already exists")

            policy = AdminApprovalPolicy()
            decision = await policy.evaluate(request, conn)

            password_hash = hash_password(request.password)
            row = await create_user(
                conn,
                request.username,
                password_hash,
                request.display_name,
                decision.status,
                decision.is_admin,
            )
            user_id = str(row["id"]) if row else ""
            user_status = row["status"] if row else "pending"

    # 连接释放后写事件（EventStore使用独立连接池）
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
        payload=event_payload.model_dump(mode="json"),
        correlation_id=user_id,
    )
    await event_store.append(event)
    await event_bus.publish(EventType.UserRegistered, event_payload.model_dump(mode="json"))

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
    pool: asyncpg.Pool = Depends(_get_pool),
    settings: Settings = Depends(get_settings),
) -> UserResponse:
    """用户登录：pending/rejected返回403，密码错误返回401"""
    async with pool.acquire() as conn:
        row = await get_user_by_username(conn, request.username)
        if not row:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        if row["status"] == "pending":
            raise HTTPException(status_code=403, detail="Account pending admin approval")
        if row["status"] == "rejected":
            raise HTTPException(status_code=403, detail="Account registration was rejected")

        if not verify_password(request.password, row["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid credentials")

        user_id = str(row["id"])
        token = create_access_token(
            user_id=user_id,
            username=row["username"],
            display_name=row["display_name"],
            is_admin=row["is_admin"],
            settings=settings,
        )
        return UserResponse(
            user_id=user_id,
            username=row["username"],
            display_name=row["display_name"],
            access_token=token,
        )


@router.get("/users/pending", response_model=list[PendingUserResponse])
async def list_pending(
    admin: User = Depends(require_admin_dependency),
    pool: asyncpg.Pool = Depends(_get_pool),
) -> list[PendingUserResponse]:
    """列出待审批用户，仅is_admin可访问"""
    async with pool.acquire() as conn:
        rows = await list_pending_users(conn)
        return [
            PendingUserResponse(
                user_id=str(r["id"]),
                username=r["username"],
                display_name=r["display_name"],
                status=r["status"],
                created_at=r["created_at"],
            )
            for r in rows
        ]


@router.post("/users/{user_id}/approve", response_model=ApprovalResponse)
async def approve_user(
    user_id: str,
    admin: User = Depends(require_admin_dependency),
    pool: asyncpg.Pool = Depends(_get_pool),
) -> ApprovalResponse:
    """管理员审批用户：pending→active"""
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await get_user_by_id(conn, uuid.UUID(user_id))
            if not row:
                raise HTTPException(status_code=404, detail="User not found")
            if row["status"] == "active":
                raise HTTPException(status_code=400, detail="User is already active")
            if row["status"] == "rejected":
                raise HTTPException(status_code=400, detail="User was already rejected")

            await update_user_status(conn, uuid.UUID(user_id), "active")

        return ApprovalResponse(
            user_id=user_id,
            username=row["username"],
            display_name=row["display_name"],
            status="active",
        )


@router.post("/users/{user_id}/reject", response_model=ApprovalResponse)
async def reject_user(
    user_id: str,
    body: RejectionRequest | None = None,
    admin: User = Depends(require_admin_dependency),
    pool: asyncpg.Pool = Depends(_get_pool),
) -> ApprovalResponse:
    """管理员拒绝用户：pending→rejected"""
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await get_user_by_id(conn, uuid.UUID(user_id))
            if not row:
                raise HTTPException(status_code=404, detail="User not found")
            if row["status"] == "active":
                raise HTTPException(status_code=400, detail="User is already active")
            if row["status"] == "rejected":
                raise HTTPException(status_code=400, detail="User was already rejected")

            await update_user_status(conn, uuid.UUID(user_id), "rejected")

        reason = body.reason if body else None
        return ApprovalResponse(
            user_id=user_id,
            username=row["username"],
            display_name=row["display_name"],
            status="rejected",
            reason=reason,
        )
