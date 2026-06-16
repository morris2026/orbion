"""PostgreSQL测试基础设施：共享fixture、统一client fixture

env/DB/app.state清理由根conftest _clean_env fixture统一处理。
此处只保留测试专用fixture（client/user_repo_provider/event_bus等），
client fixture只负责资源关闭，不再删除app.state（根conftest兜底）。
"""

from collections.abc import AsyncGenerator

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient

from app.biz.agents.adapters.base import ModelOutput, PromptInput
from app.biz.agents.declarations import BUILTIN_AGENT_DECLARATIONS
from app.biz.agents.runtime import AgentRuntime
from app.biz.agents.scheduler import AgentScheduler
from app.biz.agents.service import AgentService
from app.biz.agents.templates import AgentTemplateManager
from app.biz.credentials.service import CredentialService
from app.biz.files.service import FileService
from app.biz.git.service import GitService
from app.biz.projects.read_repo import ProjectReadProtocol, load_project_read_impl
from app.biz.projects.service import ProjectService
from app.biz.repos.service import RepoService
from app.biz.threads.read_repo import load_thread_read_impl
from app.biz.threads.service import ThreadService
from app.config import get_settings
from app.hub.auth.repository import UserRepositoryProvider, load_user_repo_provider
from app.hub.channels.sse import SSEChannel
from app.hub.events.bus import InProcessEventBus
from app.hub.events.projections import load_projections_impl
from app.hub.events.store import load_store_impl
from app.main import app


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
    settings = get_settings()
    provider_cls = load_user_repo_provider(settings.user_repo)
    provider = provider_cls()
    await provider.connect()
    yield provider
    await provider.close()


@pytest.fixture
async def sse_channel(event_bus: InProcessEventBus, project_read_for_sse: ProjectReadProtocol) -> SSEChannel:
    """SSEChannel——直接SSE单元测试使用，不依赖HTTP client"""
    return SSEChannel(event_bus, project_read_for_sse)


@pytest.fixture
async def project_read_for_sse() -> AsyncGenerator[ProjectReadProtocol, None]:
    """ProjectReadProtocol实例，供SSEChannel查询用户项目列表"""
    settings = get_settings()
    read_cls = load_project_read_impl(settings.project_read)
    project_read = read_cls()
    await project_read.connect()
    yield project_read
    await project_read.close()


@pytest.fixture
async def client(
    event_bus: InProcessEventBus,
    user_repo_provider: UserRepositoryProvider,
    sse_channel: SSEChannel,
) -> AsyncGenerator[AsyncClient, None]:
    """httpx AsyncClient，初始化app.state的全部属性。

    teardown时关闭资源并delete全部属性，消除全局状态污染。
    """
    settings = get_settings()
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

    project_service = ProjectService(event_store, event_bus, project_read, settings)
    thread_service = ThreadService(event_store, event_bus, thread_read, project_read)

    stub_adapter = StubAdapter()
    agent_runtime = AgentRuntime(event_bus, event_store, stub_adapter)
    agent_scheduler = AgentScheduler(event_bus, agent_runtime)
    agent_service = AgentService(event_store, event_bus, agent_runtime)

    agent_template_manager = AgentTemplateManager(settings)
    for agent_type, declaration in BUILTIN_AGENT_DECLARATIONS.items():
        agent_template_manager.ensure_template(agent_type, declaration.model_dump(), "")

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
    app.state.agent_template_manager = agent_template_manager
    app.state.credential_service = CredentialService(settings)
    app.state.repo_service = RepoService(settings, app.state.credential_service, app.state.thread_service)
    app.state.file_service = FileService(settings)
    app.state.git_service = GitService(settings, event_bus, projections)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    # teardown: 关闭资源（逆序），app.state由根conftest兜底清理
    agent_scheduler.close()
    await thread_read.close()
    await project_read.close()
    await projections.close()
    await event_store.close()


# -- DB fixture --


@pytest.fixture
async def postgres_pool() -> AsyncGenerator[asyncpg.Pool, None]:
    """PostgreSQL连接池（临时：seeding/cleanup绕过抽象层直接操作DB）"""
    pool = await asyncpg.create_pool(get_settings().postgres.url, min_size=1, max_size=5)
    yield pool
    await pool.close()


@pytest.fixture
async def db_conn() -> AsyncGenerator[asyncpg.Connection, None]:
    """共享DB连接fixture——根conftest _clean_env已做动态TRUNCATE，此处只提供连接"""
    conn = await asyncpg.connect(get_settings().postgres.url)
    yield conn
    await conn.close()
