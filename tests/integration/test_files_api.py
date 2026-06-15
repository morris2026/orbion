"""文件操作 API 集成测试 — MVP-RE-2.3, 2.3a, 2.4, 2.5, 2.6, 2.7, 2.8"""

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
        user_id=user.id, username=user.username, display_name=user.display_name, is_admin=False, settings=get_settings()
    )
    return {"id": user.id, "token": token}


async def _create_project(
    client: AsyncClient, token: str, event_bus: InProcessEventBus, name: str = "FileTestProject"
) -> str:
    resp = await client.post("/projects", json={"name": name}, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    await event_bus.wait_for_pending()
    return str(resp.json()["id"])


async def _add_repo(client: AsyncClient, token: str, project_id: str, name: str = "testrepo") -> None:
    resp = await client.post(
        f"/projects/{project_id}/repos", json={"name": name}, headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 201


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class TestMvpRe2FilesApi:
    async def test_mvp_re_2_3_read_file(
        self, client: AsyncClient, user_repo_provider: UserRepositoryProvider, event_bus: InProcessEventBus
    ) -> None:
        """MVP-RE-2.3：读取文件内容"""
        user = await _create_user(user_repo_provider, "fileuser1")
        project_id = await _create_project(client, user["token"], event_bus)
        await _add_repo(client, user["token"], project_id)
        # git init 创建空仓库，先写入文件再读取
        await client.put(
            f"/projects/{project_id}/repos/testrepo/files",
            params={"path": "README.md"},
            json={"content": "# Hello Orbion"},
            headers=_auth(user["token"]),
        )
        resp = await client.get(
            f"/projects/{project_id}/repos/testrepo/files", params={"path": "README.md"}, headers=_auth(user["token"])
        )
        assert resp.status_code == 200
        assert "Orbion" in resp.json()["content"]

    async def test_mvp_re_2_4_read_nonexistent_file(
        self, client: AsyncClient, user_repo_provider: UserRepositoryProvider, event_bus: InProcessEventBus
    ) -> None:
        """MVP-RE-2.4：读取不存在的文件返回 404"""
        user = await _create_user(user_repo_provider, "fileuser2")
        project_id = await _create_project(client, user["token"], event_bus)
        await _add_repo(client, user["token"], project_id)
        resp = await client.get(
            f"/projects/{project_id}/repos/testrepo/files",
            params={"path": "nonexistent.ts"},
            headers=_auth(user["token"]),
        )
        assert resp.status_code == 404

    async def test_mvp_re_2_5_save_file(
        self, client: AsyncClient, user_repo_provider: UserRepositoryProvider, event_bus: InProcessEventBus
    ) -> None:
        """MVP-RE-2.5：保存文件内容"""
        user = await _create_user(user_repo_provider, "fileuser3")
        project_id = await _create_project(client, user["token"], event_bus)
        await _add_repo(client, user["token"], project_id)
        # 先创建初始文件
        await client.put(
            f"/projects/{project_id}/repos/testrepo/files",
            params={"path": "README.md"},
            json={"content": "initial"},
            headers=_auth(user["token"]),
        )
        resp = await client.put(
            f"/projects/{project_id}/repos/testrepo/files",
            params={"path": "README.md"},
            json={"content": "updated content"},
            headers=_auth(user["token"]),
        )
        assert resp.status_code == 200

        read_resp = await client.get(
            f"/projects/{project_id}/repos/testrepo/files",
            params={"path": "README.md"},
            headers=_auth(user["token"]),
        )
        assert read_resp.json()["content"] == "updated content"

    async def test_mvp_re_2_6_save_new_file(
        self, client: AsyncClient, user_repo_provider: UserRepositoryProvider, event_bus: InProcessEventBus
    ) -> None:
        """MVP-RE-2.6：保存新建文件"""
        user = await _create_user(user_repo_provider, "fileuser4")
        project_id = await _create_project(client, user["token"], event_bus)
        await _add_repo(client, user["token"], project_id)
        resp = await client.put(
            f"/projects/{project_id}/repos/testrepo/files",
            params={"path": "src/new-file.ts"},
            json={"content": "new file content"},
            headers=_auth(user["token"]),
        )
        assert resp.status_code == 200

        read_resp = await client.get(
            f"/projects/{project_id}/repos/testrepo/files",
            params={"path": "src/new-file.ts"},
            headers=_auth(user["token"]),
        )
        assert read_resp.json()["content"] == "new file content"

    async def test_mvp_re_2_3a_read_file_head_version(
        self, client: AsyncClient, user_repo_provider: UserRepositoryProvider, event_bus: InProcessEventBus
    ) -> None:
        """MVP-RE-2.3a：ref=HEAD 读取已提交版本"""
        user = await _create_user(user_repo_provider, "fileuser7")
        project_id = await _create_project(client, user["token"], event_bus)
        await _add_repo(client, user["token"], project_id)
        # 写入文件并提交
        await client.put(
            f"/projects/{project_id}/repos/testrepo/files",
            params={"path": "notes.txt"},
            json={"content": "v1"},
            headers=_auth(user["token"]),
        )
        # git commit (通过 git service API 或直接操作)
        settings = get_settings()
        import git

        repo = git.Repo(str(settings.project_repo_path(project_id, "testrepo")))
        repo.index.add(["notes.txt"])
        repo.index.commit("init")
        # 修改工作区但不提交
        await client.put(
            f"/projects/{project_id}/repos/testrepo/files",
            params={"path": "notes.txt"},
            json={"content": "v2"},
            headers=_auth(user["token"]),
        )
        # ref=HEAD 应返回 v1
        resp = await client.get(
            f"/projects/{project_id}/repos/testrepo/files",
            params={"path": "notes.txt", "ref": "HEAD"},
            headers=_auth(user["token"]),
        )
        assert resp.status_code == 200
        assert resp.json()["content"] == "v1"

    async def test_mvp_re_2_7_path_traversal(
        self, client: AsyncClient, user_repo_provider: UserRepositoryProvider, event_bus: InProcessEventBus
    ) -> None:
        """MVP-RE-2.7：路径穿越攻击返回 403"""
        user = await _create_user(user_repo_provider, "fileuser8")
        project_id = await _create_project(client, user["token"], event_bus, "PathTraversalProject")
        await _add_repo(client, user["token"], project_id)
        resp = await client.get(
            f"/projects/{project_id}/repos/testrepo/files",
            params={"path": "../../../etc/passwd"},
            headers=_auth(user["token"]),
        )
        assert resp.status_code == 403

    async def test_mvp_re_2_8_non_member_forbidden(
        self, client: AsyncClient, user_repo_provider: UserRepositoryProvider, event_bus: InProcessEventBus
    ) -> None:
        """MVP-RE-2.8：非项目成员返回 403"""
        user = await _create_user(user_repo_provider, "fileuser5")
        other = await _create_user(user_repo_provider, "fileuser6")
        project_id = await _create_project(client, user["token"], event_bus, "FilePrivateProject")
        await _add_repo(client, user["token"], project_id)
        resp = await client.get(
            f"/projects/{project_id}/repos/testrepo/files",
            params={"path": "README.md"},
            headers=_auth(other["token"]),
        )
        assert resp.status_code == 403
