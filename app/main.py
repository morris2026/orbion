"""Orbion MVP FastAPI应用入口"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI

from app.config import get_settings
from app.hub.auth.repository import load_user_repo_impl
from app.hub.auth.routes import router as auth_router
from app.hub.channels.static import mount_static_files
from app.hub.events.bus import InProcessEventBus
from app.hub.events.store import load_store_impl


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    # 共享连接池
    app.state.pool = await asyncpg.create_pool(settings.postgres.url, min_size=2, max_size=10)
    # EventStore + EventBus 初始化
    store_cls = load_store_impl("postgres")
    app.state.event_store = store_cls()
    await app.state.event_store.connect()
    app.state.event_bus = InProcessEventBus()
    # UserRepository实现类（每次请求创建新实例）
    app.state.user_repo_cls = load_user_repo_impl("postgres")
    yield
    await app.state.event_store.close()
    await app.state.pool.close()


app = FastAPI(title="Orbion MVP", lifespan=lifespan)

# 认证模块
app.include_router(auth_router, prefix="/auth", tags=["auth"])

# 静态文件挂载必须在所有API路由之后
mount_static_files(app)
