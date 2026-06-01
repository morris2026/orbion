"""Orbion MVP FastAPI应用入口"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.biz.projects.read_repo import load_project_read_impl
from app.biz.projects.routes import router as project_router
from app.biz.projects.service import ProjectService
from app.config import get_settings
from app.hub.auth.repository import load_user_repo_provider
from app.hub.auth.routes import router as auth_router
from app.hub.channels.static import mount_static_files
from app.hub.events.bus import InProcessEventBus
from app.hub.events.projections import load_projections_impl
from app.hub.events.store import load_store_impl


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    # EventStore + EventBus 初始化
    store_cls = load_store_impl(settings.event_store)
    app.state.event_store = store_cls()
    await app.state.event_store.connect()
    app.state.event_bus = InProcessEventBus()
    # Projections 初始化（订阅EventBus，写端依赖其handler）
    proj_cls = load_projections_impl(settings.event_projections)
    app.state.event_projections = proj_cls(app.state.event_bus)
    await app.state.event_projections.connect()
    # ProjectRead 初始化（self-managed pool，读端）
    read_cls = load_project_read_impl(settings.project_read)
    app.state.project_read = read_cls()
    await app.state.project_read.connect()
    # ProjectService 初始化（纯依赖注入，无pool）
    app.state.project_service = ProjectService(app.state.event_store, app.state.event_bus, app.state.project_read)
    # UserRepositoryProvider 初始化
    provider_cls = load_user_repo_provider(settings.user_repo)
    app.state.user_repo_provider = provider_cls()
    await app.state.user_repo_provider.connect()
    yield
    await app.state.event_projections.close()
    await app.state.event_store.close()
    await app.state.project_read.close()
    await app.state.user_repo_provider.close()


app = FastAPI(title="Orbion MVP", lifespan=lifespan)

# 认证模块
app.include_router(auth_router, prefix="/auth", tags=["auth"])

# 项目模块
app.include_router(project_router, prefix="/projects", tags=["projects"])

# 静态文件挂载必须在所有API路由之后
mount_static_files(app)
