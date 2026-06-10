"""项目与成员管理API集成测试：MVP-9.1–MVP-9.7 + MVP-8.8/8.9/8.11/8.12"""

import uuid
from typing import Any

import asyncpg
import pytest
from httpx import AsyncClient

from app.config import get_settings
from app.hub.auth.repository import UserRepositoryProvider
from app.hub.auth.service import create_access_token, hash_password
from app.hub.events.bus import InProcessEventBus
from app.hub.permissions.roles import HUMAN_ROLE_BITS

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
        settings=get_settings(),
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


# -- MVP-9 测试 --


class TestCreateProject:
    """MVP-9.1: 创建项目→创建者自动成为Owner"""

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
    """MVP-9.2: 列出用户参与的项目含role字段"""

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
    """MVP-9.3: 项目详情→非成员返回404"""

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
    """MVP-9.4: 添加成员→默认Member角色"""

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
    """MVP-9.5: 非Owner/Admin添加成员→403"""

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
    """MVP-9.6: 项目创建事件链路 — ProjectCreated 含创建者信息"""

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
    """MVP-9.7: MANAGE_MEMBERS权限位显式验证"""

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


# -- MVP-8 API测试（require_permission未实现，待后续可测试）--


class TestRequirePermissionAllowed:
    """MVP-8.8: require_permission有权限→请求继续"""

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
    """MVP-8.9: require_permission无权限→403"""

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
    """MVP-8.11: Admin角色权限验证"""

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
    """MVP-8.12: 错误响应格式统一验证"""

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


class TestListMembers:
    """MVP-9补充: 成员列表端点 — 验证创建者自动成为Owner + 添加成员可见"""

    @pytest.mark.asyncio
    async def test_list_members_after_project_creation(
        self, client: AsyncClient, event_bus: InProcessEventBus, user_repo_provider: UserRepositoryProvider
    ) -> None:
        """创建项目后成员列表包含Owner"""
        owner = await _create_user(user_repo_provider, "listmem_owner")
        project_id = await _create_project(client, owner["token"])
        await event_bus.wait_for_pending()

        resp = await client.get(
            f"/projects/{project_id}/members", headers={"Authorization": f"Bearer {owner['token']}"}
        )
        assert resp.status_code == 200
        members = resp.json()
        assert len(members) >= 1
        owner_members = [m for m in members if m["participant_id"] == owner["id"]]
        assert len(owner_members) == 1
        assert owner_members[0]["role"] == "owner"
        assert owner_members[0]["type"] == "human"
        assert owner_members[0]["display_name"] == owner["display_name"]

    @pytest.mark.asyncio
    async def test_list_members_includes_added_member(
        self, client: AsyncClient, event_bus: InProcessEventBus, user_repo_provider: UserRepositoryProvider
    ) -> None:
        """添加成员后列表可见"""
        owner = await _create_user(user_repo_provider, "listmem2_owner")
        new_member = await _create_user(user_repo_provider, "listmem2_member")
        project_id = await _create_project(client, owner["token"])
        await event_bus.wait_for_pending()

        await client.post(
            f"/projects/{project_id}/members",
            json={"user_id": new_member["id"], "role": "member"},
            headers={"Authorization": f"Bearer {owner['token']}"},
        )
        await event_bus.wait_for_pending()

        resp = await client.get(
            f"/projects/{project_id}/members", headers={"Authorization": f"Bearer {owner['token']}"}
        )
        assert resp.status_code == 200
        members = resp.json()
        assert len(members) >= 2
        added = [m for m in members if m["participant_id"] == new_member["id"]]
        assert len(added) == 1
        assert added[0]["role"] == "member"

    @pytest.mark.asyncio
    async def test_list_members_non_member_404(
        self, client: AsyncClient, event_bus: InProcessEventBus, user_repo_provider: UserRepositoryProvider
    ) -> None:
        """非项目成员请求成员列表→404"""
        owner = await _create_user(user_repo_provider, "listmem3_owner")
        outsider = await _create_user(user_repo_provider, "listmem3_out")
        project_id = await _create_project(client, owner["token"])
        await event_bus.wait_for_pending()

        resp = await client.get(
            f"/projects/{project_id}/members", headers={"Authorization": f"Bearer {outsider['token']}"}
        )
        assert resp.status_code == 404


class TestProjectNameUniqueness:
    """项目名称唯一校验 → 409"""

    @pytest.mark.asyncio
    async def test_duplicate_project_name_returns_409(
        self, client: AsyncClient, event_bus: InProcessEventBus, user_repo_provider: UserRepositoryProvider
    ) -> None:
        """同名项目创建→409"""
        user = await _create_user(user_repo_provider, "dup_proj_user")
        await _create_project(client, user["token"], "SameName")
        await event_bus.wait_for_pending()

        resp = await client.post(
            "/projects",
            json={"name": "SameName"},
            headers={"Authorization": f"Bearer {user['token']}"},
        )
        assert resp.status_code == 409
        assert "detail" in resp.json()

    @pytest.mark.asyncio
    async def test_different_user_duplicate_name_returns_409(
        self, client: AsyncClient, event_bus: InProcessEventBus, user_repo_provider: UserRepositoryProvider
    ) -> None:
        """不同用户创建同名项目→409"""
        user1 = await _create_user(user_repo_provider, "dup_proj_user1")
        user2 = await _create_user(user_repo_provider, "dup_proj_user2")
        await _create_project(client, user1["token"], "UniqueName")
        await event_bus.wait_for_pending()

        resp = await client.post(
            "/projects",
            json={"name": "UniqueName"},
            headers={"Authorization": f"Bearer {user2['token']}"},
        )
        assert resp.status_code == 409


class TestAtomicProjectCreation:
    """项目创建原子操作：项目+默认线程"""

    @pytest.mark.asyncio
    async def test_create_project_includes_default_thread(
        self,
        client: AsyncClient,
        db_conn: asyncpg.Connection,
        event_bus: InProcessEventBus,
        user_repo_provider: UserRepositoryProvider,
    ) -> None:
        """创建项目返回default_thread_id，投影写入线程记录"""
        user = await _create_user(user_repo_provider, "atomic_user")
        resp = await client.post(
            "/projects",
            json={"name": "AtomicProject"},
            headers={"Authorization": f"Bearer {user['token']}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["default_thread_id"] is not None

        project_id = data["id"]
        thread_id = data["default_thread_id"]
        await event_bus.wait_for_pending()

        # threads表有默认线程记录
        row = await db_conn.fetchrow(
            "SELECT title, type, status FROM threads WHERE id = $1",
            uuid.UUID(thread_id),
        )
        assert row is not None
        assert row["title"] == "AtomicProject"
        assert row["type"] == "discussion"

        # projects表有default_thread_id列
        proj_row = await db_conn.fetchrow(
            "SELECT default_thread_id FROM projects WHERE id = $1",
            uuid.UUID(project_id),
        )
        assert proj_row is not None
        assert str(proj_row["default_thread_id"]) == thread_id

    @pytest.mark.asyncio
    async def test_project_list_includes_default_thread_id(
        self, client: AsyncClient, event_bus: InProcessEventBus, user_repo_provider: UserRepositoryProvider
    ) -> None:
        """项目列表包含default_thread_id"""
        user = await _create_user(user_repo_provider, "list_dt_user")
        await _create_project(client, user["token"], "DTProject")
        await event_bus.wait_for_pending()

        resp = await client.get("/projects", headers={"Authorization": f"Bearer {user['token']}"})
        assert resp.status_code == 200
        projects = resp.json()
        found = [p for p in projects if p["name"] == "DTProject"]
        assert len(found) == 1
        assert found[0]["default_thread_id"] is not None
