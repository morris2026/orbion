"""Orbion MVP FastAPI应用入口"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.biz.agents.adapters.base import ModelAdapter, ModelOutput, PromptInput
from app.biz.agents.adapters.claude import ClaudeAdapter
from app.biz.agents.memory import AgentMemory
from app.biz.agents.routes import router as agent_router
from app.biz.agents.runtime import AgentRuntime
from app.biz.agents.scheduler import AgentScheduler
from app.biz.agents.service import AgentService
from app.biz.git.service import GitService
from app.biz.outputs.routes import output_action_router, output_list_router
from app.biz.outputs.service import OutputService
from app.biz.plans.routes import plan_action_router, plan_list_router
from app.biz.plans.service import PlanService
from app.biz.projects.read_repo import load_project_read_impl
from app.biz.projects.routes import router as project_router
from app.biz.projects.service import ProjectService
from app.biz.threads.read_repo import load_thread_read_impl
from app.biz.threads.routes import message_router, thread_router
from app.biz.threads.service import ThreadService
from app.config import get_settings
from app.hub.auth.repository import load_user_repo_provider
from app.hub.auth.routes import router as auth_router
from app.hub.channels.routes import router as sse_router
from app.hub.channels.sse import SSEChannel
from app.hub.channels.static import mount_static_files
from app.hub.events.bus import InProcessEventBus
from app.hub.events.projections import load_projections_impl
from app.hub.events.store import load_store_impl


class StubModelAdapter:
    """测试环境fallback adapter——无api_key时使用"""

    async def complete(self, prompt: PromptInput) -> ModelOutput:
        raise NotImplementedError("需配置 anthropic_api_key 才能调用 ClaudeAdapter")


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
    # ThreadRead 初始化（self-managed pool，读端）
    thread_read_cls = load_thread_read_impl(settings.thread_read)
    app.state.thread_read = thread_read_cls()
    await app.state.thread_read.connect()
    # ThreadService 初始化（纯依赖注入，无pool）
    app.state.thread_service = ThreadService(
        app.state.event_store, app.state.event_bus, app.state.thread_read, app.state.project_read
    )
    # UserRepositoryProvider 初始化
    provider_cls = load_user_repo_provider(settings.user_repo)
    app.state.user_repo_provider = provider_cls()
    await app.state.user_repo_provider.connect()
    # SSEChannel 初始化（订阅EventBus）
    app.state.sse_channel = SSEChannel(app.state.event_bus)
    # AgentRuntime + AgentScheduler + AgentService 初始化
    if settings.anthropic_api_key:
        adapter: ModelAdapter = ClaudeAdapter(api_key=settings.anthropic_api_key)
    else:
        adapter = StubModelAdapter()
    agent_memory = AgentMemory(settings.memory_base_path)
    app.state.agent_runtime = AgentRuntime(app.state.event_bus, app.state.event_store, adapter, agent_memory)
    app.state.agent_scheduler = AgentScheduler(app.state.event_bus, app.state.agent_runtime)
    app.state.agent_service = AgentService(app.state.event_store, app.state.event_bus, app.state.agent_runtime)
    # PlanService 初始化（纯依赖注入，依赖projections做读端查询）
    app.state.plan_service = PlanService(app.state.event_store, app.state.event_bus, app.state.event_projections)
    # OutputService 初始化（纯依赖注入，依赖projections做读端查询）
    app.state.output_service = OutputService(app.state.event_store, app.state.event_bus, app.state.event_projections)
    # GitService 初始化（订阅TaskOutputApproved事件，审批通过后自动commit）
    app.state.git_service = GitService(settings.repo_path, app.state.event_bus, app.state.event_projections)
    yield
    app.state.agent_scheduler.close()
    await app.state.thread_read.close()
    await app.state.event_projections.close()
    await app.state.event_store.close()
    await app.state.project_read.close()
    await app.state.user_repo_provider.close()


app = FastAPI(title="Orbion MVP", lifespan=lifespan)

# 认证模块
app.include_router(auth_router, prefix="/auth", tags=["auth"])

# 项目模块
app.include_router(project_router, prefix="/projects", tags=["projects"])

# Agent模块 — Agent端点嵌套在项目路径下
app.include_router(agent_router, prefix="/projects", tags=["agents"])

# 计划模块 — 列表端点嵌套在项目路径下，审批端点在plans路径下
app.include_router(plan_list_router, prefix="/projects", tags=["plans"])
app.include_router(plan_action_router, prefix="/plans", tags=["plans"])

# 产出模块 — 列表端点嵌套在项目路径下，操作端点在outputs路径下
app.include_router(output_list_router, prefix="/projects", tags=["outputs"])
app.include_router(output_action_router, prefix="/outputs", tags=["outputs"])

# 线程模块 — 线程端点嵌套在项目路径下
app.include_router(thread_router, prefix="/projects/{project_id}/threads", tags=["threads"])

# 消息模块 — 消息端点嵌套在线程路径下
app.include_router(message_router, prefix="/threads/{thread_id}/messages", tags=["messages"])

# SSE流 — 事件推送端点
app.include_router(sse_router, prefix="/events", tags=["events"])

# 静态文件挂载必须在所有API路由之后
mount_static_files(app)
