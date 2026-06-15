"""git-log 支持 repo_name 查询参数 — 解决 3.5 验证缺失"""

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
    client: AsyncClient, token: str, event_bus: InProcessEventBus, name: str = "GitLogRepoProject"
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


class TestGitLogRepoName:
    async def test_git_log_with_repo_name(
        self, client: AsyncClient, user_repo_provider: UserRepositoryProvider, event_bus: InProcessEventBus
    ) -> None:
        """git-log 支持 repo_name 查询参数，返回指定仓库的 commit 历史"""
        user = await _create_user(user_repo_provider, "glruser1")
        project_id = await _create_project(client, user["token"], event_bus, "GitLogRepoProject")
        await _add_repo(client, user["token"], project_id)
        # 写入文件并 commit
        await client.put(
            f"/projects/{project_id}/repos/testrepo/files",
            params={"path": "hello.txt"},
            json={"content": "world"},
            headers=_auth(user["token"]),
        )
        await client.post(
            f"/projects/{project_id}/repos/testrepo/stage",
            json={"paths": ["hello.txt"]},
            headers=_auth(user["token"]),
        )
        await client.post(
            f"/projects/{project_id}/repos/testrepo/commit",
            json={"message": "add hello.txt"},
            headers=_auth(user["token"]),
        )
        # 通过 git-log + repo_name 查询
        resp = await client.get(
            f"/git/{project_id}/git-log",
            params={"repo_name": "testrepo"},
            headers=_auth(user["token"]),
        )
        assert resp.status_code == 200
        messages = [c["message"] for c in resp.json()]
        assert any("add hello.txt" in m for m in messages)
