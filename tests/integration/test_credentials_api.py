"""凭据管理 API 集成测试 — CRUD + 仓库自动认证"""

import pytest
from httpx import AsyncClient

from app.config import get_settings
from app.hub.auth.repository import UserRepositoryProvider
from app.hub.auth.service import create_access_token, hash_password
from app.hub.events.bus import InProcessEventBus

pytestmark = pytest.mark.asyncio


async def _create_user(provider: UserRepositoryProvider, username: str) -> dict[str, str]:
    async with provider.scoped() as repo:
        user = await repo.create_user(username, hash_password("testpass123"), username.capitalize(), "active", False)
    token = create_access_token(
        user_id=user.id,
        username=user.username,
        display_name=user.display_name,
        is_admin=user.is_admin,
        settings=get_settings(),
    )
    return {"id": user.id, "token": token}


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_project(
    client: AsyncClient, token: str, event_bus: InProcessEventBus, name: str = "CredTestProject"
) -> str:
    resp = await client.post("/projects", json={"name": name}, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    await event_bus.wait_for_pending()
    return str(resp.json()["id"])


class TestCredentialCRUD:
    """凭据创建/列表/删除 API"""

    async def test_create_and_list_credentials(
        self, client: AsyncClient, user_repo_provider: UserRepositoryProvider
    ) -> None:
        """创建凭据后列表包含该凭据，且不含 token"""
        user = await _create_user(user_repo_provider, "creduser1")
        headers = _auth(user["token"])

        # 创建
        resp = await client.post(
            "/users/me/credentials",
            json={"type": "github", "name": "我的GitHub", "token": "ghp_test123"},
            headers=headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["type"] == "github"
        assert data["name"] == "我的GitHub"
        assert "token" not in data

        # 列表
        list_resp = await client.get("/users/me/credentials", headers=headers)
        assert list_resp.status_code == 200
        creds = list_resp.json()
        assert len(creds) == 1
        assert creds[0]["type"] == "github"
        assert "token" not in creds[0]

    async def test_delete_credential(self, client: AsyncClient, user_repo_provider: UserRepositoryProvider) -> None:
        """删除凭据后列表不再包含"""
        user = await _create_user(user_repo_provider, "creduser2")
        headers = _auth(user["token"])

        resp = await client.post(
            "/users/me/credentials",
            json={"type": "github", "name": "ToDelete", "token": "ghp_del"},
            headers=headers,
        )
        assert resp.status_code == 201
        cred_id = resp.json()["id"]

        # 删除
        del_resp = await client.delete(f"/users/me/credentials/{cred_id}", headers=headers)
        assert del_resp.status_code == 204

        # 确认删除
        list_resp = await client.get("/users/me/credentials", headers=headers)
        assert list_resp.status_code == 200
        assert len(list_resp.json()) == 0


class TestSSHUrlRejection:
    """SSH URL 添加仓库被拒绝"""

    async def test_git_at_url_rejected(
        self,
        client: AsyncClient,
        user_repo_provider: UserRepositoryProvider,
        event_bus: InProcessEventBus,
    ) -> None:
        """git@ 开头的 SSH URL 返回 400"""
        user = await _create_user(user_repo_provider, "ssh_reject_user")
        project_id = await _create_project(client, user["token"], event_bus, "SSHRejectProject")

        resp = await client.post(
            f"/projects/{project_id}/repos",
            json={"url": "git@github.com:user/repo.git"},
            headers=_auth(user["token"]),
        )
        assert resp.status_code == 400
        assert "SSH" in resp.json()["detail"]

    async def test_ssh_protocol_url_rejected(
        self,
        client: AsyncClient,
        user_repo_provider: UserRepositoryProvider,
        event_bus: InProcessEventBus,
    ) -> None:
        """ssh:// 开头的 URL 返回 400"""
        user = await _create_user(user_repo_provider, "ssh_proto_user")
        project_id = await _create_project(client, user["token"], event_bus, "SSHProtoProject")

        resp = await client.post(
            f"/projects/{project_id}/repos",
            json={"url": "ssh://git@github.com/user/repo.git"},
            headers=_auth(user["token"]),
        )
        assert resp.status_code == 400
        assert "SSH" in resp.json()["detail"]


class TestCloneErrorNoStderrLeak:
    """clone 失败不泄露内部 stderr 信息"""

    async def test_clone_failure_returns_generic_error(
        self,
        client: AsyncClient,
        user_repo_provider: UserRepositoryProvider,
        event_bus: InProcessEventBus,
    ) -> None:
        """clone 失败返回通用错误信息，不包含 stderr 细节"""
        user = await _create_user(user_repo_provider, "no_stderr_user")
        project_id = await _create_project(client, user["token"], event_bus, "NoStderrProject")

        resp = await client.post(
            f"/projects/{project_id}/repos",
            json={"url": "https://invalid.host.example/nonexistent.git", "name": "fail-repo"},
            headers=_auth(user["token"]),
        )
        assert resp.status_code == 400
        detail = resp.json()["detail"]
        # 不应包含 git 的内部错误输出
        assert "stderr" not in detail.lower()
        assert "fatal" not in detail.lower()
        assert "检查" in detail
