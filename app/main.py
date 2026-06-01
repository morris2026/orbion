"""Orbion MVP FastAPI应用入口"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import get_settings
from app.hub.auth.repository import load_user_repo_provider
from app.hub.auth.routes import router as auth_router
from app.hub.channels.static import mount_static_files
from app.hub.events.bus import InProcessEventBus
from app.hub.events.store import load_store_impl


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    # EventStore + EventBus 初始化（实现名从配置读取）
    store_cls = load_store_impl(settings.event_store)
    app.state.event_store = store_cls()
    await app.state.event_store.connect()
    app.state.event_bus = InProcessEventBus()
    # UserRepositoryProvider 初始化（实现名从配置读取）
    provider_cls = load_user_repo_provider(settings.user_repo)
    app.state.user_repo_provider = provider_cls()
    await app.state.user_repo_provider.connect()
    yield
    await app.state.event_store.close()
    await app.state.user_repo_provider.close()


app = FastAPI(title="Orbion MVP", lifespan=lifespan)

# 认证模块
app.include_router(auth_router, prefix="/auth", tags=["auth"])

# 静态文件挂载必须在所有API路由之后
mount_static_files(app)
