"""Agent管理API集成测试：TC-12.1、TC-12.8、TC-12.9、TC-12.12"""

from collections.abc import AsyncGenerator
from typing import Any

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient

from app.biz.agents.adapters.base import ModelOutput, PromptInput
from app.biz.agents.runtime import AgentRuntime
from app.biz.agents.service import AgentService
from app.biz.projects.read_repo import load_project_read_impl
from app.biz.projects.service import ProjectService
from app.biz.threads.read_repo import load_thread_read_impl
from app.biz.threads.service import ThreadService
from app.config import get_settings
from app.hub.auth.repository import UserRepositoryProvider, load_user_repo_provider
from app.hub.auth.service import create_access_token, hash_password
from app.hub.events.bus import InProcessEventBus
from app.hub.events.projections import load_projections_impl
from app.hub.events.store import load_store_impl
from app.main import app

settings = get_settings()


class StubAdapter:
    """MVP stub adapter——API测试不需要LLM调用"""

    async def complete(self, prompt: PromptInput) -> ModelOutput:
        return ModelOutput(content="stub output")


@pytest.fixture
async def event_bus() -> InProcessEventBus:
    return InProcessEventBus()


@pytest.fixture
async def user_repo_provider() -> AsyncGenerator[UserRepositoryProvider, None]:
    provider_cls = load_user_repo_provider(settings.user_repo)
    provider = provider_cls()
    await provider.connect()
    yield provider
    await provider.close()


@pytest.fixture
async def client(
    event_bus: InProcessEventBus,
    user_repo_provider: UserRepositoryProvider,
) -> AsyncGenerator[AsyncClient, None]:
    """httpx AsyncClient，初始化app.state（含AgentRuntime/AgentScheduler）"""
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
    agent_service = AgentService(event_store, event_bus, agent_runtime)

    app.state.event_store = event_store
    app.state.event_bus = event_bus
    app.state.event_projections = projections
    app.state.project_read = project_read
    app.state.project_service = project_service
    app.state.thread_read = thread_read
    app.state.thread_service = thread_service
    app.state.user_repo_provider = user_repo_provider
    app.state.agent_runtime = agent_runtime
    app.state.agent_service = agent_service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    await projections.close()
    await thread_read.close()
    await project_read.close()
    await event_store.close()


async def _create_user(provider: UserRepositoryProvider, username: str, is_admin: bool = False) -> dict[str, Any]:
    async with provider.scoped() as repo:
        user = await repo.create_user(username, hash_password("testpass123"), username.capitalize(), "active", is_admin)
    token = create_access_token(
        user_id=user.id,
        username=user.username,
        display_name=user.display_name,
        is_admin=user.is_admin,
        settings=settings,
    )
    return {"id": user.id, "token": token, "username": user.username, "display_name": user.display_name}


async def _create_project(client: AsyncClient, token: str) -> dict[str, Any]:
    resp = await client.post(
        "/projects", json={"name": "TestProject", "description": "test"}, headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    return dict(resp.json())


# -- TC-12.1: 注册Agent→project_members投影+权限位自动分配 --


async def test_tc12_1_register_agent(
    client: AsyncClient,
    event_bus: InProcessEventBus,
    user_repo_provider: UserRepositoryProvider,
    db_conn: asyncpg.Connection,
) -> None:
    """TC-12.1: POST /projects/{id}/agents→AgentResponse + project_members投影有Agent成员"""
    admin = await _create_user(user_repo_provider, "agentadmin", is_admin=True)
    project = await _create_project(client, admin["token"])
    await event_bus.wait_for_pending()

    resp = await client.post(
        f"/projects/{project['id']}/agents",
        json={"agent_type": "summary", "model_id": "claude-haiku-4-5-20251001", "display_name": "总结助手"},
        headers={"Authorization": f"Bearer {admin['token']}"},
    )
    assert resp.status_code == 200
    data = dict(resp.json())
    assert data["type"] == "agent"
    assert data["agent_type"] == "summary"
    assert data["model_id"] == "claude-haiku-4-5-20251001"
    assert data["status"] == "idle"
    assert data["subscribed_events"] == ["DiscussionMessageCreated"]
    assert data["roles"] == 4  # AGENT_ROLE_BITS["summary"] = 4
    assert data["participant_id"].startswith("agent-summary-")

    # 检查project_members投影有Agent成员
    await event_bus.wait_for_pending()
    row = await db_conn.fetchrow(
        "SELECT participant_id, type, agent_type, roles, status FROM project_members "
        "WHERE project_id = $1 AND type = 'agent'",
        project["id"],
    )
    assert row is not None
    assert row["type"] == "agent"
    assert row["agent_type"] == "summary"
    assert int(row["roles"]) == 4
    assert row["status"] == "idle"


# -- TC-12.8: Agent列表含状态 --


async def test_tc12_8_agent_list(
    client: AsyncClient,
    event_bus: InProcessEventBus,
    user_repo_provider: UserRepositoryProvider,
    db_conn: asyncpg.Connection,
) -> None:
    """TC-12.8: GET /projects/{id}/agents→返回列表含每个Agent的status字段"""
    admin = await _create_user(user_repo_provider, "listadmin", is_admin=True)
    project = await _create_project(client, admin["token"])
    await event_bus.wait_for_pending()

    # 注册summary Agent
    resp = await client.post(
        f"/projects/{project['id']}/agents",
        json={"agent_type": "summary", "model_id": "claude-haiku", "display_name": "总结助手"},
        headers={"Authorization": f"Bearer {admin['token']}"},
    )
    assert resp.status_code == 200
    await event_bus.wait_for_pending()

    # 注册decompose Agent
    resp = await client.post(
        f"/projects/{project['id']}/agents",
        json={"agent_type": "decompose", "model_id": "claude-haiku", "display_name": "分解助手"},
        headers={"Authorization": f"Bearer {admin['token']}"},
    )
    assert resp.status_code == 200
    await event_bus.wait_for_pending()

    resp = await client.get(
        f"/projects/{project['id']}/agents",
        headers={"Authorization": f"Bearer {admin['token']}"},
    )
    assert resp.status_code == 200
    agents = resp.json()
    assert len(agents) == 2
    for agent in agents:
        assert "status" in agent
        assert agent["status"] == "idle"


# -- TC-12.9: Agent详细状态 --


async def test_tc12_9_agent_status(
    client: AsyncClient,
    event_bus: InProcessEventBus,
    user_repo_provider: UserRepositoryProvider,
    db_conn: asyncpg.Connection,
) -> None:
    """TC-12.9: GET /projects/{id}/agents/{id}/status→AgentStatus含completed_count/error_count"""
    admin = await _create_user(user_repo_provider, "statusadmin", is_admin=True)
    project = await _create_project(client, admin["token"])
    await event_bus.wait_for_pending()

    resp = await client.post(
        f"/projects/{project['id']}/agents",
        json={"agent_type": "summary", "model_id": "claude-haiku", "display_name": "总结助手"},
        headers={"Authorization": f"Bearer {admin['token']}"},
    )
    await event_bus.wait_for_pending()
    agent_id = dict(resp.json())["participant_id"]

    resp = await client.get(
        f"/projects/{project['id']}/agents/{agent_id}/status",
        headers={"Authorization": f"Bearer {admin['token']}"},
    )
    assert resp.status_code == 200
    status_data = dict(resp.json())
    assert status_data["agent_id"] == agent_id
    assert status_data["status"] == "idle"
    assert status_data["completed_count"] == 0
    assert status_data["error_count"] == 0
    assert status_data["current_task"] is None


# -- TC-12.12: Agent管理API权限检查 --


async def test_tc12_12_permission_check(
    client: AsyncClient,
    event_bus: InProcessEventBus,
    user_repo_provider: UserRepositoryProvider,
    db_conn: asyncpg.Connection,
) -> None:
    """TC-12.12: Member角色POST /projects/{id}/agents→403（需MANAGE_AGENTS权限）"""
    admin = await _create_user(user_repo_provider, "permadmin", is_admin=True)
    project = await _create_project(client, admin["token"])
    await event_bus.wait_for_pending()

    # Member角色用户（roles=31，不含MANAGE_AGENTS=256）
    member = await _create_user(user_repo_provider, "permmember", is_admin=False)
    # admin添加member到项目
    await client.post(
        f"/projects/{project['id']}/members",
        json={"user_id": member["id"], "role": "member"},
        headers={"Authorization": f"Bearer {admin['token']}"},
    )
    await event_bus.wait_for_pending()

    # member尝试注册Agent→403
    resp = await client.post(
        f"/projects/{project['id']}/agents",
        json={"agent_type": "summary", "model_id": "claude-haiku", "display_name": "总结助手"},
        headers={"Authorization": f"Bearer {member['token']}"},
    )
    assert resp.status_code == 403
