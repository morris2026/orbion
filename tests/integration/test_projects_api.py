"""项目与成员管理API集成测试：TC-9.1–TC-9.7 + TC-8.8/8.9/8.11/8.12"""

import uuid
from collections.abc import AsyncGenerator
from typing import Any

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient

from app.biz.projects.read_repo import load_project_read_impl
from app.biz.projects.service import ProjectService
from app.config import get_settings
from app.hub.auth.repository import UserRepositoryProvider, load_user_repo_provider
from app.hub.auth.service import create_access_token, hash_password
from app.hub.events.bus import InProcessEventBus
from app.hub.events.projections import load_projections_impl
from app.hub.events.store import load_store_impl
from app.hub.permissions.roles import HUMAN_ROLE_BITS
from app.main import app

settings = get_settings()


# -- fixture --


@pytest.fixture
async def db_conn() -> AsyncGenerator[asyncpg.Connection, None]:
    """每个测试独立的DB连接，测试后清理projects/project_members/users/event_log"""
    conn = await asyncpg.connect(settings.postgres.url)
    yield conn
    await conn.execute("DELETE FROM project_members")
    await conn.execute("DELETE FROM projects")
    await conn.execute("DELETE FROM event_log WHERE event_type IN ('MemberAdded', 'ProjectCreated')")
    await conn.execute("DELETE FROM users")
    await conn.close()


@pytest.fixture
async def user_repo_provider() -> AsyncGenerator[UserRepositoryProvider, None]:
    provider_cls = load_user_repo_provider(settings.user_repo)
    provider = provider_cls()
    await provider.connect()
    yield provider
    await provider.close()


@pytest.fixture
async def event_bus() -> InProcessEventBus:
    """InProcessEventBus实例，供写操作后等待投影完成"""
    return InProcessEventBus()


@pytest.fixture
async def client(
    event_bus: InProcessEventBus, user_repo_provider: UserRepositoryProvider
) -> AsyncGenerator[AsyncClient, None]:
    """httpx AsyncClient，初始化app.state"""
    store_cls = load_store_impl(settings.event_store)
    event_store = store_cls()
    await event_store.connect()
    # Projections 初始化（必须先于 ProjectService）
    proj_cls = load_projections_impl(settings.event_projections)
    projections = proj_cls(event_bus)
    await projections.connect()
    # ProjectRead 初始化
    read_cls = load_project_read_impl(settings.project_read)
    project_read = read_cls()
    await project_read.connect()
    # ProjectService 初始化（纯依赖注入，无 pool）
    project_service = ProjectService(event_store, event_bus, project_read)
    app.state.event_store = event_store
    app.state.event_bus = event_bus
    app.state.event_projections = projections
    app.state.project_read = project_read
    app.state.project_service = project_service
    app.state.user_repo_provider = user_repo_provider

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    await projections.close()
    await project_read.close()
    await event_store.close()


# -- helper --


async def _create_user(provider: UserRepositoryProvider, username: str, is_admin: bool = False) -> dict[str, Any]:
    """创建active用户并返回{id, token, username, display_name, is_admin}"""
    async with provider.scoped() as repo:
        user = await repo.create_user(username, hash_password("testpass123"), username.capitalize(), "active", is_admin)
    token = create_access_token(
        user_id=user.id,
        username=user.username,
        display_name=user.display_name,
        is_admin=user.is_admin,
        settings=settings,
    )
    return {
        "id": user.id,
        "token": token,
        "username": user.username,
        "display_name": user.display_name,
        "is_admin": user.is_admin,
    }


async def _create_project(
    client: AsyncClient, token: str, name: str = "Test Project", description: str | None = None
) -> str:
    """创建项目并返回project_id"""
    resp = await client.post(
        "/projects", json={"name": name, "description": description}, headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    return str(resp.json()["id"])


# -- TC-9 测试 --


class TestCreateProject:
    """TC-9.1: 创建项目→创建者自动成为Owner"""

    @pytest.mark.asyncio
    async def test_create_project_owner(
        self,
        client: AsyncClient,
        db_conn: asyncpg.Connection,
        event_bus: InProcessEventBus,
        user_repo_provider: UserRepositoryProvider,
    ) -> None:
        user = await _create_user(user_repo_provider, "proj_owner")
        project_id = await _create_project(client, user["token"])
        await event_bus.wait_for_pending()

        resp = await client.get(f"/projects/{project_id}", headers={"Authorization": f"Bearer {user['token']}"})
        data = resp.json()
        assert data["name"] == "Test Project"
        assert data["tenant_id"] == "default"

        # project_members有Owner记录（roles=4095）
        row = await db_conn.fetchrow(
            "SELECT roles FROM project_members WHERE participant_id = $1 AND project_id = $2", user["id"], project_id
        )
        assert row is not None
        assert int(row["roles"]) == HUMAN_ROLE_BITS["owner"]


class TestListProjects:
    """TC-9.2: 列出用户参与的项目含role字段"""

    @pytest.mark.asyncio
    async def test_list_projects_with_role(
        self, client: AsyncClient, event_bus: InProcessEventBus, user_repo_provider: UserRepositoryProvider
    ) -> None:
        user = await _create_user(user_repo_provider, "proj_lister")
        project_id = await _create_project(client, user["token"])
        await event_bus.wait_for_pending()

        resp = await client.get("/projects", headers={"Authorization": f"Bearer {user['token']}"})
        assert resp.status_code == 200
        data = resp.json()
        found = [p for p in data if p["id"] == project_id]
        assert len(found) == 1
        assert found[0]["role"] == "owner"


class TestProjectDetail:
    """TC-9.3: 项目详情→非成员返回404"""

    @pytest.mark.asyncio
    async def test_project_detail_member_and_nonmember(
        self, client: AsyncClient, event_bus: InProcessEventBus, user_repo_provider: UserRepositoryProvider
    ) -> None:
        owner = await _create_user(user_repo_provider, "detail_owner")
        outsider = await _create_user(user_repo_provider, "detail_out")
        project_id = await _create_project(client, owner["token"])
        await event_bus.wait_for_pending()

        # 成员可看
        resp = await client.get(f"/projects/{project_id}", headers={"Authorization": f"Bearer {owner['token']}"})
        assert resp.status_code == 200

        # 非成员返回404
        resp = await client.get(f"/projects/{project_id}", headers={"Authorization": f"Bearer {outsider['token']}"})
        assert resp.status_code == 404


class TestAddMember:
    """TC-9.4: 添加成员→默认Member角色"""

    @pytest.mark.asyncio
    async def test_add_member_default_role(
        self,
        client: AsyncClient,
        db_conn: asyncpg.Connection,
        event_bus: InProcessEventBus,
        user_repo_provider: UserRepositoryProvider,
    ) -> None:
        owner = await _create_user(user_repo_provider, "member_owner")
        new_member = await _create_user(user_repo_provider, "member_new")
        project_id = await _create_project(client, owner["token"])
        await event_bus.wait_for_pending()

        resp = await client.post(
            f"/projects/{project_id}/members",
            json={"user_id": new_member["id"], "role": "member"},
            headers={"Authorization": f"Bearer {owner['token']}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["participant_id"] == new_member["id"]
        assert data["project_id"] == project_id
        assert data["type"] == "human"
        assert data["role"] == "member"
        await event_bus.wait_for_pending()

        # project_members有Member记录（roles=31）
        row = await db_conn.fetchrow(
            "SELECT roles FROM project_members WHERE participant_id = $1 AND project_id = $2",
            new_member["id"],
            project_id,
        )
        assert row is not None
        assert int(row["roles"]) == HUMAN_ROLE_BITS["member"]


class TestAddMemberPermission:
    """TC-9.5: 非Owner/Admin添加成员→403"""

    @pytest.mark.asyncio
    async def test_member_cannot_add_member(
        self, client: AsyncClient, event_bus: InProcessEventBus, user_repo_provider: UserRepositoryProvider
    ) -> None:
        owner = await _create_user(user_repo_provider, "perm_owner")
        member_user = await _create_user(user_repo_provider, "perm_member")
        target = await _create_user(user_repo_provider, "perm_target")
        project_id = await _create_project(client, owner["token"])
        await event_bus.wait_for_pending()

        # 先添加member
        await client.post(
            f"/projects/{project_id}/members",
            json={"user_id": member_user["id"], "role": "member"},
            headers={"Authorization": f"Bearer {owner['token']}"},
        )
        await event_bus.wait_for_pending()

        # member尝试添加成员→403
        resp = await client.post(
            f"/projects/{project_id}/members",
            json={"user_id": target["id"], "role": "member"},
            headers={"Authorization": f"Bearer {member_user['token']}"},
        )
        assert resp.status_code == 403


class TestProjectEventChain:
    """TC-9.6: 项目创建事件链路 — ProjectCreated 含创建者信息"""

    @pytest.mark.asyncio
    async def test_create_project_event_chain(
        self,
        client: AsyncClient,
        db_conn: asyncpg.Connection,
        event_bus: InProcessEventBus,
        user_repo_provider: UserRepositoryProvider,
    ) -> None:
        user = await _create_user(user_repo_provider, "chain_user")
        project_id = await _create_project(client, user["token"])
        await event_bus.wait_for_pending()

        # EventStore有ProjectCreated事件（创建者信息在payload中，不再有单独的MemberAdded）
        rows = await db_conn.fetch("SELECT event_type FROM event_log WHERE project_id = $1", project_id)
        event_types = [r["event_type"] for r in rows]
        assert "ProjectCreated" in event_types

        # project_members投影有Owner数据（由ProjectCreated handler原子插入）
        row = await db_conn.fetchrow(
            "SELECT type FROM project_members WHERE participant_id = $1 AND project_id = $2", user["id"], project_id
        )
        assert row is not None
        assert row["type"] == "human"


class TestManageMembersPermissionBit:
    """TC-9.7: MANAGE_MEMBERS权限位显式验证"""

    @pytest.mark.asyncio
    async def test_viewer_cannot_add_member(
        self, client: AsyncClient, event_bus: InProcessEventBus, user_repo_provider: UserRepositoryProvider
    ) -> None:
        owner = await _create_user(user_repo_provider, "bit_owner")
        viewer = await _create_user(user_repo_provider, "bit_viewer")
        target = await _create_user(user_repo_provider, "bit_target")
        project_id = await _create_project(client, owner["token"])
        await event_bus.wait_for_pending()

        # 添加viewer
        await client.post(
            f"/projects/{project_id}/members",
            json={"user_id": viewer["id"], "role": "viewer"},
            headers={"Authorization": f"Bearer {owner['token']}"},
        )
        await event_bus.wait_for_pending()

        # viewer尝试添加成员→403
        resp = await client.post(
            f"/projects/{project_id}/members",
            json={"user_id": target["id"], "role": "member"},
            headers={"Authorization": f"Bearer {viewer['token']}"},
        )
        assert resp.status_code == 403


# -- TC-8 API测试（步骤9实现require_permission后可测试）--


class TestRequirePermissionAllowed:
    """TC-8.8: require_permission有权限→请求继续"""

    @pytest.mark.asyncio
    async def test_owner_has_approve_plan(
        self, client: AsyncClient, event_bus: InProcessEventBus, user_repo_provider: UserRepositoryProvider
    ) -> None:
        """Owner（含ADMINISTRATOR）通过MANAGE_MEMBERS权限检查"""
        owner = await _create_user(user_repo_provider, "tc8_owner")
        project_id = await _create_project(client, owner["token"])
        await event_bus.wait_for_pending()

        # Owner可以添加成员（MANAGE_MEMBERS权限）
        target = await _create_user(user_repo_provider, "tc8_target")
        resp = await client.post(
            f"/projects/{project_id}/members",
            json={"user_id": target["id"], "role": "viewer"},
            headers={"Authorization": f"Bearer {owner['token']}"},
        )
        assert resp.status_code == 200


class TestRequirePermissionDenied:
    """TC-8.9: require_permission无权限→403"""

    @pytest.mark.asyncio
    async def test_viewer_no_manage_members(
        self, client: AsyncClient, event_bus: InProcessEventBus, user_repo_provider: UserRepositoryProvider
    ) -> None:
        """Viewer没有MANAGE_MEMBERS权限→403"""
        owner = await _create_user(user_repo_provider, "tc9_owner")
        viewer = await _create_user(user_repo_provider, "tc9_viewer")
        target = await _create_user(user_repo_provider, "tc9_target2")
        project_id = await _create_project(client, owner["token"])
        await event_bus.wait_for_pending()
        await client.post(
            f"/projects/{project_id}/members",
            json={"user_id": viewer["id"], "role": "viewer"},
            headers={"Authorization": f"Bearer {owner['token']}"},
        )
        await event_bus.wait_for_pending()

        resp = await client.post(
            f"/projects/{project_id}/members",
            json={"user_id": target["id"], "role": "member"},
            headers={"Authorization": f"Bearer {viewer['token']}"},
        )
        assert resp.status_code == 403


class TestAdminRolePermission:
    """TC-8.11: Admin角色权限验证"""

    @pytest.mark.asyncio
    async def test_admin_can_manage_members(
        self, client: AsyncClient, event_bus: InProcessEventBus, user_repo_provider: UserRepositoryProvider
    ) -> None:
        """Admin有MANAGE_MEMBERS权限，可以添加成员"""
        owner = await _create_user(user_repo_provider, "tc11_owner")
        admin_user = await _create_user(user_repo_provider, "tc11_admin")
        target = await _create_user(user_repo_provider, "tc11_target")
        project_id = await _create_project(client, owner["token"])
        await event_bus.wait_for_pending()

        # 添加Admin角色成员
        await client.post(
            f"/projects/{project_id}/members",
            json={"user_id": admin_user["id"], "role": "admin"},
            headers={"Authorization": f"Bearer {owner['token']}"},
        )
        await event_bus.wait_for_pending()

        # Admin可以添加成员
        resp = await client.post(
            f"/projects/{project_id}/members",
            json={"user_id": target["id"], "role": "member"},
            headers={"Authorization": f"Bearer {admin_user['token']}"},
        )
        assert resp.status_code == 200


class TestErrorResponseFormat:
    """TC-8.12: 错误响应格式统一验证"""

    @pytest.mark.asyncio
    async def test_401_no_jwt(self, client: AsyncClient) -> None:
        """无JWT→401，格式{"detail":"..."}"""
        resp = await client.get("/projects")
        assert resp.status_code == 401
        data = resp.json()
        assert "detail" in data

    @pytest.mark.asyncio
    async def test_403_insufficient_permission(
        self, client: AsyncClient, event_bus: InProcessEventBus, user_repo_provider: UserRepositoryProvider
    ) -> None:
        """权限不足→403，格式{"detail":"..."}"""
        owner = await _create_user(user_repo_provider, "tc12_owner")
        viewer = await _create_user(user_repo_provider, "tc12_viewer")
        target = await _create_user(user_repo_provider, "tc12_target")
        project_id = await _create_project(client, owner["token"])
        await event_bus.wait_for_pending()
        await client.post(
            f"/projects/{project_id}/members",
            json={"user_id": viewer["id"], "role": "viewer"},
            headers={"Authorization": f"Bearer {owner['token']}"},
        )
        await event_bus.wait_for_pending()

        resp = await client.post(
            f"/projects/{project_id}/members",
            json={"user_id": target["id"], "role": "member"},
            headers={"Authorization": f"Bearer {viewer['token']}"},
        )
        assert resp.status_code == 403
        data = resp.json()
        assert "detail" in data

    @pytest.mark.asyncio
    async def test_404_project_not_found(self, client: AsyncClient, user_repo_provider: UserRepositoryProvider) -> None:
        """资源不存在→404，格式{"detail":"..."}"""
        user = await _create_user(user_repo_provider, "tc12_user")
        fake_id = str(uuid.uuid4())
        resp = await client.get(f"/projects/{fake_id}", headers={"Authorization": f"Bearer {user['token']}"})
        assert resp.status_code == 404
        data = resp.json()
        assert "detail" in data

    @pytest.mark.asyncio
    async def test_409_duplicate_member(
        self, client: AsyncClient, event_bus: InProcessEventBus, user_repo_provider: UserRepositoryProvider
    ) -> None:
        """重复添加成员→409，格式{"detail":"..."}"""
        owner = await _create_user(user_repo_provider, "tc12d_owner")
        target = await _create_user(user_repo_provider, "tc12d_target")
        project_id = await _create_project(client, owner["token"])
        await event_bus.wait_for_pending()
        await client.post(
            f"/projects/{project_id}/members",
            json={"user_id": target["id"], "role": "member"},
            headers={"Authorization": f"Bearer {owner['token']}"},
        )
        await event_bus.wait_for_pending()

        # 重复添加同一成员→409
        resp = await client.post(
            f"/projects/{project_id}/members",
            json={"user_id": target["id"], "role": "member"},
            headers={"Authorization": f"Bearer {owner['token']}"},
        )
        assert resp.status_code == 409
        data = resp.json()
        assert "detail" in data
