"""PostgreSQL测试基础设施：共享连接池、清理fixture、统一client fixture

Why: 4个测试文件各自定义client fixture，只设置部分app.state属性；
--randomly随机化执行顺序时，前一个测试的fixture残留 CLOSED 对象污染app.state，
导致后一个只设置了3个属性的client fixture遇到 stale projections/project_read 等报错。
统一fixture设置所有app.state属性 + teardown时delete全部属性，彻底消除全局状态污染。
"""

from collections.abc import AsyncGenerator

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient

from app.biz.agents.adapters.base import ModelOutput, PromptInput
from app.biz.agents.runtime import AgentRuntime
from app.biz.agents.scheduler import AgentScheduler
from app.biz.agents.service import AgentService
from app.biz.projects.read_repo import load_project_read_impl
from app.biz.projects.service import ProjectService
from app.biz.threads.read_repo import load_thread_read_impl
from app.biz.threads.service import ThreadService
from app.config import get_settings
from app.hub.auth.repository import UserRepositoryProvider, load_user_repo_provider
from app.hub.channels.sse import SSEChannel
from app.hub.events.bus import InProcessEventBus
from app.hub.events.projections import load_projections_impl
from app.hub.events.store import load_store_impl
from app.main import app

settings = get_settings()

# -- 所有app.state属性的完整列表，用于teardown清理 --
_APP_STATE_ATTRS = [
    "event_store",
    "event_bus",
    "event_projections",
    "project_read",
    "project_service",
    "thread_read",
    "thread_service",
    "user_repo_provider",
    "sse_channel",
    "agent_runtime",
    "agent_scheduler",
    "agent_service",
]


class StubAdapter:
    """集成测试stub adapter——不需要真实LLM调用，返回固定ModelOutput"""

    async def complete(self, prompt: PromptInput) -> ModelOutput:
        return ModelOutput(content="stub output")


# -- 共享fixture --


@pytest.fixture
async def event_bus() -> InProcessEventBus:
    """InProcessEventBus实例，供写操作后等待投影完成"""
    return InProcessEventBus()


@pytest.fixture
async def user_repo_provider() -> AsyncGenerator[UserRepositoryProvider, None]:
    """UserRepositoryProvider——连接真实PostgreSQL做用户CRUD"""
    provider_cls = load_user_repo_provider(settings.user_repo)
    provider = provider_cls()
    await provider.connect()
    yield provider
    await provider.close()


@pytest.fixture
async def sse_channel(event_bus: InProcessEventBus) -> SSEChannel:
    """SSEChannel——直接SSE单元测试使用，不依赖HTTP client"""
    return SSEChannel(event_bus)


@pytest.fixture
async def client(
    event_bus: InProcessEventBus,
    user_repo_provider: UserRepositoryProvider,
    sse_channel: SSEChannel,
) -> AsyncGenerator[AsyncClient, None]:
    """httpx AsyncClient，初始化app.state的全部属性。

    设置所有app.state属性（event_store/event_bus/event_projections/
    project_read/project_service/thread_read/thread_service/
    user_repo_provider/sse_channel/agent_runtime/agent_scheduler/agent_service），
    teardown时关闭资源并delete全部属性，消除全局状态污染。
    """
    store_cls = load_store_impl(settings.event_store)
    event_store = store_cls()
    await event_store.connect()

    proj_cls = load_projections_impl(settings.event_projections)
    projections = proj_cls(event_bus)
    await projections.connect()

    read_cls = load_project_read_impl(settings.project_read)
    project_read = read_cls()
    await project_read.connect()

    thread_read_cls = load_thread_read_impl(settings.thread_read)
    thread_read = thread_read_cls()
    await thread_read.connect()

    project_service = ProjectService(event_store, event_bus, project_read)
    thread_service = ThreadService(event_store, event_bus, thread_read, project_read)

    stub_adapter = StubAdapter()
    agent_runtime = AgentRuntime(event_bus, event_store, stub_adapter)
    agent_scheduler = AgentScheduler(event_bus, agent_runtime)
    agent_service = AgentService(event_store, event_bus, agent_runtime)

    app.state.event_store = event_store
    app.state.event_bus = event_bus
    app.state.event_projections = projections
    app.state.project_read = project_read
    app.state.project_service = project_service
    app.state.thread_read = thread_read
    app.state.thread_service = thread_service
    app.state.user_repo_provider = user_repo_provider
    app.state.sse_channel = sse_channel
    app.state.agent_runtime = agent_runtime
    app.state.agent_scheduler = agent_scheduler
    app.state.agent_service = agent_service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    # teardown: 关闭资源（逆序），然后删除app.state全部属性防止污染
    agent_scheduler.close()
    await thread_read.close()
    await project_read.close()
    await projections.close()
    await event_store.close()
    # 删除所有app.state属性，确保下一个测试不会看到 stale CLOSED 对象
    for attr in _APP_STATE_ATTRS:
        try:
            delattr(app.state, attr)
        except AttributeError:
            pass


# -- DB fixture --


@pytest.fixture
async def postgres_pool() -> AsyncGenerator[asyncpg.Pool, None]:
    """PostgreSQL连接池（临时：seeding/cleanup绕过抽象层直接操作DB）"""
    pool = await asyncpg.create_pool(get_settings().postgres.url, min_size=1, max_size=5)
    yield pool
    await pool.close()


@pytest.fixture
async def db_conn() -> AsyncGenerator[asyncpg.Connection, None]:
    """共享DB连接fixture：测试前后清空所有业务表"""
    conn = await asyncpg.connect(get_settings().postgres.url)
    await conn.execute("TRUNCATE event_log CASCADE")
    await conn.execute(
        "TRUNCATE task_outputs, execution_plans, thread_messages, project_members, threads, projects, users CASCADE"
    )
    yield conn
    await conn.execute("TRUNCATE event_log CASCADE")
    await conn.execute(
        "TRUNCATE task_outputs, execution_plans, thread_messages, project_members, threads, projects, users CASCADE"
    )
    await conn.close()


@pytest.fixture(autouse=True, scope="function")
async def _clean_test_tables() -> None:
    """自动清理所有业务表，确保每个测试从干净数据库开始
    Why: TRUNCATE CASCADE比DELETE FROM更可靠——自动处理FK依赖并重置序列；
    间歇性--randomly失败证明DELETE FROM在跨fixture并发时不够可靠
    """
    conn = await asyncpg.connect(get_settings().postgres.url)
    # event_log无FK依赖，先单独TRUNCATE
    await conn.execute("TRUNCATE event_log CASCADE")
    # 其余表按FK依赖从叶子到根TRUNCATE
    await conn.execute(
        "TRUNCATE task_outputs, execution_plans, thread_messages, project_members, threads, projects, users CASCADE"
    )
    await conn.close()
