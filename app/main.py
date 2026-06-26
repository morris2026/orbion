"""Orbion MVP FastAPI应用入口"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI

from app.biz.agent_models.routes import (
    project_router as agent_model_project_router,
)
from app.biz.agent_models.routes import (
    user_router as agent_model_user_router,
)
from app.biz.agents.adapters.base import ModelAdapter, ModelOutput, PromptInput
from app.biz.agents.adapters.claude import ClaudeAdapter
from app.biz.agents.declarations import BUILTIN_AGENT_DECLARATIONS
from app.biz.agents.memory import AgentMemory
from app.biz.agents.routes import router as agent_router
from app.biz.agents.runtime import AgentRuntime
from app.biz.agents.scheduler import AgentScheduler
from app.biz.agents.service import AgentService
from app.biz.agents.templates import AgentTemplateManager
from app.biz.credentials.routes import router as credential_router
from app.biz.credentials.service import CredentialService
from app.biz.files.routes import router as file_router
from app.biz.files.service import FileService
from app.biz.git.routes import router as git_router
from app.biz.git.routes import sc_router as git_sc_router
from app.biz.git.service import GitService
from app.biz.outputs.routes import output_action_router, output_list_router
from app.biz.outputs.service import OutputService
from app.biz.plans.routes import plan_action_router, plan_list_router
from app.biz.plans.service import PlanService
from app.biz.projects.read_repo import load_project_read_impl
from app.biz.projects.routes import router as project_router
from app.biz.projects.service import ProjectService
from app.biz.repos.routes import router as repo_router
from app.biz.repos.service import RepoService
from app.biz.threads.read_repo import load_thread_read_impl
from app.biz.threads.routes import message_router, thread_router
from app.biz.threads.service import ThreadService
from app.biz.user_models.routes import router as user_model_router
from app.biz.worktree.routes import router as worktree_router
from app.biz.worktree.worktree_service import WorktreeService
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
    # ORBION_ENCRYPTION_KEY 启动自检（AR-2.2）：缺失则拒绝启动
    from app.biz.user_models.encryption import validate_encryption_key

    validate_encryption_key()
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
    app.state.project_service = ProjectService(
        app.state.event_store, app.state.event_bus, app.state.project_read, settings
    )
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
    # SSEChannel 初始化（订阅EventBus，用户级连接需读端查询用户项目列表）
    app.state.sse_channel = SSEChannel(app.state.event_bus, app.state.project_read)
    # AgentRuntime + AgentScheduler + AgentService 初始化
    if settings.anthropic_api_key:
        adapter: ModelAdapter = ClaudeAdapter(api_key=settings.anthropic_api_key)
    else:
        adapter = StubModelAdapter()
    agent_memory = AgentMemory(settings)
    app.state.agent_runtime = AgentRuntime(app.state.event_bus, app.state.event_store, adapter, agent_memory)
    app.state.agent_scheduler = AgentScheduler(app.state.event_bus, app.state.agent_runtime)
    app.state.agent_service = AgentService(app.state.event_store, app.state.event_bus, app.state.agent_runtime)
    # AgentTemplateManager 初始化（确保3个内置Agent模板文件存在）
    app.state.agent_template_manager = AgentTemplateManager(settings)
    for agent_type, declaration in BUILTIN_AGENT_DECLARATIONS.items():
        app.state.agent_template_manager.ensure_template(agent_type, declaration.model_dump(), "")
    # PlanService 初始化（纯依赖注入，依赖projections做读端查询）
    app.state.plan_service = PlanService(app.state.event_store, app.state.event_bus, app.state.event_projections)
    # OutputService 初始化（纯依赖注入，依赖projections做读端查询）
    app.state.output_service = OutputService(app.state.event_store, app.state.event_bus, app.state.event_projections)
    # GitService 初始化（订阅TaskOutputApproved事件，审批通过后自动commit）
    app.state.git_service = GitService(settings, app.state.event_bus, app.state.event_projections)
    # CredentialService 初始化（凭据加密存储）
    app.state.credential_service = CredentialService(settings)
    # 主连接池（设计 §1.1：min_size=5, max_size=20，各 service 共享，避免连接数膨胀）
    _db_pool = await asyncpg.create_pool(settings.postgres.url, min_size=5, max_size=20)
    # UserModelService + AgentModelMappingService 初始化（AR-2.x）
    from app.biz.agent_models.service import AgentModelMappingService
    from app.biz.agent_models.store import AgentModelStore
    from app.biz.user_models.service import UserModelService

    app.state.user_model_service = UserModelService(_db_pool)
    app.state.agent_model_mapping_service = AgentModelMappingService(
        AgentModelStore(settings.root_dir),
        app.state.user_model_service,
        settings.projects_dir,
    )
    # RepoService 初始化（仓库扫描/添加/删除，依赖CredentialService+ThreadService）
    app.state.repo_service = RepoService(settings, app.state.credential_service, app.state.thread_service)
    # FileService 初始化（文件树/读取/保存）
    app.state.file_service = FileService(settings)
    # WorktreeService 初始化（worktree 生命周期管理 + 事件发布）
    # MVP: TaskResolver 用 stub（tasks 表尚未实现），list/get/file 操作可用；
    # create_or_reuse/delete_by_owner/merge 需 agent-runtime 提供 PostgresTaskResolver
    import uuid as _uuid

    from app.biz.git.git_service import GitCommandService as _GitCmd
    from app.biz.worktree.models import TaskContext, TaskResolver

    class _StubTaskResolver(TaskResolver):
        async def resolve(self, task_id: _uuid.UUID) -> TaskContext:
            raise KeyError(f"task {task_id} 未注册（MVP stub，agent-runtime 未集成）")

    app.state.worktree_service = WorktreeService(
        _GitCmd(), settings, _db_pool, _StubTaskResolver(), event_bus=app.state.event_bus
    )
    yield
    app.state.agent_scheduler.close()
    await _db_pool.close()
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

# 仓库模块 — 仓库管理端点嵌套在项目路径下
app.include_router(repo_router, prefix="/projects", tags=["repos"])
app.include_router(credential_router, tags=["credentials"])

# UserModel + AgentModelMapping 模块（AR-2.x）
app.include_router(user_model_router, tags=["user-models"])
app.include_router(agent_model_user_router, tags=["agent-models"])
app.include_router(agent_model_project_router, tags=["agent-models"])

# 文件模块 — 文件操作端点嵌套在项目路径下
app.include_router(file_router, prefix="/projects", tags=["files"])

# Git模块 — git log查询端点
app.include_router(git_router, prefix="/git", tags=["git"])

# Source Control模块 — status/stage/unstage/commit端点嵌套在项目路径下
app.include_router(git_sc_router, prefix="/projects", tags=["source-control"])

# Worktree模块 — worktree管理 + 文件操作 API 嵌套在项目路径下
app.include_router(worktree_router, prefix="/projects", tags=["worktrees"])

# 线程模块 — 线程端点嵌套在项目路径下
app.include_router(thread_router, prefix="/projects/{project_id}/threads", tags=["threads"])

# 消息模块 — 消息端点嵌套在线程路径下
app.include_router(message_router, prefix="/threads/{thread_id}/messages", tags=["messages"])

# SSE流 — 事件推送端点
app.include_router(sse_router, prefix="/events", tags=["events"])

# 静态文件挂载必须在所有API路由之后
mount_static_files(app)
