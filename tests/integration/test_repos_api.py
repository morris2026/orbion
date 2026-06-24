"""仓库管理 API 集成测试 — MVP-RE-1.3, 1.4, 1.5, 1.6, 1.7, 1.8"""

import subprocess
from pathlib import Path

import pytest
from httpx import AsyncClient

from app.config import get_settings
from app.hub.auth.repository import UserRepositoryProvider
from app.hub.auth.service import create_access_token, hash_password
from app.hub.events.bus import InProcessEventBus

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="session")
def upstream_bare_repo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """本地 bare 仓库作为 clone 源，替代 github.com 避免网络抖动

    Why: 直接 clone github.com 在 WSL2 GnuTLS 下偶发 TLS 中断导致 flaky。
    本 fixture 仍走 RepoService.add_repo 的 subprocess git clone 代码路径，
    仅把远端换成本地 file:// URL，验证逻辑等价。
    """
    src = tmp_path_factory.mktemp("src")
    subprocess.run(["git", "init", "-b", "main", str(src)], check=True, capture_output=True)
    (src / "README.md").write_text("# upstream\n")
    subprocess.run(["git", "-C", str(src), "add", "README.md"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(src), "-c", "user.email=u@orbion", "-c", "user.name=u", "commit", "-m", "init"],
        check=True,
        capture_output=True,
    )
    bare = tmp_path_factory.mktemp("upstream") / "Hello-World.git"
    subprocess.run(["git", "clone", "--bare", str(src), str(bare)], check=True, capture_output=True)
    return bare


async def _create_user(provider: UserRepositoryProvider, username: str, is_admin: bool = False) -> dict[str, str]:
    async with provider.scoped() as repo:
        user = await repo.create_user(username, hash_password("testpass123"), username.capitalize(), "active", is_admin)
    token = create_access_token(
        user_id=user.id,
        username=user.username,
        display_name=user.display_name,
        is_admin=user.is_admin,
        settings=get_settings(),
    )
    return {"id": user.id, "token": token}


async def _create_project(
    client: AsyncClient, token: str, event_bus: InProcessEventBus, name: str = "RepoTestProject"
) -> str:
    resp = await client.post("/projects", json={"name": name}, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    await event_bus.wait_for_pending()
    return str(resp.json()["id"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class TestMvpRe1ReposApi:
    async def test_mvp_re_1_3_add_repo_by_url(
        self,
        client: AsyncClient,
        user_repo_provider: UserRepositoryProvider,
        event_bus: InProcessEventBus,
        upstream_bare_repo: Path,
    ) -> None:
        """MVP-RE-1.3：通过 URL 添加仓库（git clone）"""
        user = await _create_user(user_repo_provider, "repouser1")
        project_id = await _create_project(client, user["token"], event_bus)
        # 用本地 file:// bare 仓库替代 github.com，消除网络抖动
        upstream_url = f"file://{upstream_bare_repo}"
        resp = await client.post(
            f"/projects/{project_id}/repos",
            json={"url": upstream_url, "name": "hello-world"},
            headers=_auth(user["token"]),
        )
        assert resp.status_code == 201
        assert resp.json()["name"] == "hello-world"

        list_resp = await client.get(f"/projects/{project_id}/repos", headers=_auth(user["token"]))
        repo_names = [r["name"] for r in list_resp.json()]
        assert "hello-world" in repo_names

    async def test_mvp_re_1_4_add_repo_by_name(
        self, client: AsyncClient, user_repo_provider: UserRepositoryProvider, event_bus: InProcessEventBus
    ) -> None:
        """MVP-RE-1.4：通过目录名添加仓库（git init）"""
        user = await _create_user(user_repo_provider, "repouser2")
        project_id = await _create_project(client, user["token"], event_bus)
        resp = await client.post(
            f"/projects/{project_id}/repos", json={"name": "my-repo"}, headers=_auth(user["token"])
        )
        assert resp.status_code == 201
        assert resp.json()["name"] == "my-repo"

    async def test_mvp_re_1_5_add_repo_duplicate_name(
        self, client: AsyncClient, user_repo_provider: UserRepositoryProvider, event_bus: InProcessEventBus
    ) -> None:
        """MVP-RE-1.5：同名目录已存在返回 400"""
        user = await _create_user(user_repo_provider, "repouser3")
        project_id = await _create_project(client, user["token"], event_bus)
        await client.post(f"/projects/{project_id}/repos", json={"name": "dup-repo"}, headers=_auth(user["token"]))
        resp = await client.post(
            f"/projects/{project_id}/repos", json={"name": "dup-repo"}, headers=_auth(user["token"])
        )
        assert resp.status_code == 400

    async def test_mvp_re_1_6_delete_repo(
        self, client: AsyncClient, user_repo_provider: UserRepositoryProvider, event_bus: InProcessEventBus
    ) -> None:
        """MVP-RE-1.6：删除仓库"""
        user = await _create_user(user_repo_provider, "repouser4")
        project_id = await _create_project(client, user["token"], event_bus)
        await client.post(f"/projects/{project_id}/repos", json={"name": "to-delete"}, headers=_auth(user["token"]))
        resp = await client.delete(f"/projects/{project_id}/repos/to-delete", headers=_auth(user["token"]))
        assert resp.status_code == 200

        list_resp = await client.get(f"/projects/{project_id}/repos", headers=_auth(user["token"]))
        repo_names = [r["name"] for r in list_resp.json()]
        assert "to-delete" not in repo_names

    async def test_mvp_re_1_7_non_member_forbidden(
        self, client: AsyncClient, user_repo_provider: UserRepositoryProvider, event_bus: InProcessEventBus
    ) -> None:
        """MVP-RE-1.7：非项目成员操作返回 403"""
        user = await _create_user(user_repo_provider, "repouser5")
        other = await _create_user(user_repo_provider, "repouser6")
        project_id = await _create_project(client, user["token"], event_bus, "PrivateRepoProject")
        resp = await client.get(f"/projects/{project_id}/repos", headers=_auth(other["token"]))
        assert resp.status_code == 403

    async def test_mvp_re_1_8_delete_nonexistent_repo(
        self, client: AsyncClient, user_repo_provider: UserRepositoryProvider, event_bus: InProcessEventBus
    ) -> None:
        """MVP-RE-1.8：删除不存在的仓库返回 404"""
        user = await _create_user(user_repo_provider, "repouser7")
        project_id = await _create_project(client, user["token"], event_bus)
        resp = await client.delete(f"/projects/{project_id}/repos/nonexistent-repo", headers=_auth(user["token"]))
        assert resp.status_code == 404
