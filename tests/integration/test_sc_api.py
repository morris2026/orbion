"""Source Control API 集成测试 — MVP-RE-3.3, 3.4, 3.5, 3.6, 3.7, 3.8"""

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
    client: AsyncClient, token: str, event_bus: InProcessEventBus, name: str = "ScTestProject"
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


class TestMvpRe3ScApi:
    async def test_mvp_re_3_3_stage_file(
        self, client: AsyncClient, user_repo_provider: UserRepositoryProvider, event_bus: InProcessEventBus
    ) -> None:
        """MVP-RE-3.3：stage 文件后从 changes 移到 staged"""
        user = await _create_user(user_repo_provider, "scuser1")
        project_id = await _create_project(client, user["token"], event_bus)
        await _add_repo(client, user["token"], project_id)
        # 写入文件（工作区修改但未stage）
        await client.put(
            f"/projects/{project_id}/repos/testrepo/files",
            params={"path": "new.txt"},
            json={"content": "hello"},
            headers=_auth(user["token"]),
        )
        # stage
        resp = await client.post(
            f"/projects/{project_id}/repos/testrepo/stage",
            json={"paths": ["new.txt"]},
            headers=_auth(user["token"]),
        )
        assert resp.status_code == 200
        # 验证 status
        status_resp = await client.get(
            f"/projects/{project_id}/repos/testrepo/status",
            headers=_auth(user["token"]),
        )
        staged_paths = [f["path"] for f in status_resp.json()["staged"]]
        assert "new.txt" in staged_paths

    async def test_mvp_re_3_4_unstage_file(
        self, client: AsyncClient, user_repo_provider: UserRepositoryProvider, event_bus: InProcessEventBus
    ) -> None:
        """MVP-RE-3.4：unstage 文件后从 staged 移到 changes"""
        user = await _create_user(user_repo_provider, "scuser2")
        project_id = await _create_project(client, user["token"], event_bus, "ScUnstageProject")
        await _add_repo(client, user["token"], project_id)
        # 写入并 stage
        await client.put(
            f"/projects/{project_id}/repos/testrepo/files",
            params={"path": "demo.txt"},
            json={"content": "demo"},
            headers=_auth(user["token"]),
        )
        await client.post(
            f"/projects/{project_id}/repos/testrepo/stage",
            json={"paths": ["demo.txt"]},
            headers=_auth(user["token"]),
        )
        # unstage
        resp = await client.post(
            f"/projects/{project_id}/repos/testrepo/unstage",
            json={"paths": ["demo.txt"]},
            headers=_auth(user["token"]),
        )
        assert resp.status_code == 200
        # 验证 status
        status_resp = await client.get(
            f"/projects/{project_id}/repos/testrepo/status",
            headers=_auth(user["token"]),
        )
        staged_paths = [f["path"] for f in status_resp.json()["staged"]]
        changes_paths = [f["path"] for f in status_resp.json()["changes"]]
        assert "demo.txt" not in staged_paths
        assert "demo.txt" in changes_paths

    async def test_mvp_re_3_5_commit(
        self, client: AsyncClient, user_repo_provider: UserRepositoryProvider, event_bus: InProcessEventBus
    ) -> None:
        """MVP-RE-3.5：commit 后 staged 清空，git log 包含新 commit"""
        user = await _create_user(user_repo_provider, "scuser3")
        project_id = await _create_project(client, user["token"], event_bus, "ScCommitProject")
        await _add_repo(client, user["token"], project_id)
        # 写入并 stage
        await client.put(
            f"/projects/{project_id}/repos/testrepo/files",
            params={"path": "commit.txt"},
            json={"content": "to commit"},
            headers=_auth(user["token"]),
        )
        await client.post(
            f"/projects/{project_id}/repos/testrepo/stage",
            json={"paths": ["commit.txt"]},
            headers=_auth(user["token"]),
        )
        # commit
        resp = await client.post(
            f"/projects/{project_id}/repos/testrepo/commit",
            json={"message": "test commit"},
            headers=_auth(user["token"]),
        )
        assert resp.status_code == 200
        assert len(resp.json()["hexsha"]) > 0
        # 验证 staged 清空
        status_resp = await client.get(
            f"/projects/{project_id}/repos/testrepo/status",
            headers=_auth(user["token"]),
        )
        assert status_resp.json()["staged"] == []
        # 验证 git log 包含新 commit
        log_resp = await client.get(
            f"/git/{project_id}/git-log",
            params={"repo_name": "testrepo"},
            headers=_auth(user["token"]),
        )
        messages = [c["message"] for c in log_resp.json()]
        assert any("test commit" in m for m in messages)

    async def test_mvp_re_3_6_commit_no_staged(
        self, client: AsyncClient, user_repo_provider: UserRepositoryProvider, event_bus: InProcessEventBus
    ) -> None:
        """MVP-RE-3.6：无 staged 文件时 commit 返回 400"""
        user = await _create_user(user_repo_provider, "scuser4")
        project_id = await _create_project(client, user["token"], event_bus, "ScEmptyCommitProject")
        await _add_repo(client, user["token"], project_id)
        resp = await client.post(
            f"/projects/{project_id}/repos/testrepo/commit",
            json={"message": "empty commit"},
            headers=_auth(user["token"]),
        )
        assert resp.status_code == 400

    async def test_mvp_re_3_7_repo_not_found(
        self, client: AsyncClient, user_repo_provider: UserRepositoryProvider, event_bus: InProcessEventBus
    ) -> None:
        """MVP-RE-3.7：不存在的仓库返回 404"""
        user = await _create_user(user_repo_provider, "scuser5")
        project_id = await _create_project(client, user["token"], event_bus, "ScNoRepoProject")
        resp = await client.get(
            f"/projects/{project_id}/repos/nonexist/status",
            headers=_auth(user["token"]),
        )
        assert resp.status_code == 404

    async def test_mvp_re_3_8_non_member_forbidden(
        self, client: AsyncClient, user_repo_provider: UserRepositoryProvider, event_bus: InProcessEventBus
    ) -> None:
        """MVP-RE-3.8：非项目成员返回 403"""
        user = await _create_user(user_repo_provider, "scuser6")
        other = await _create_user(user_repo_provider, "scuser7")
        project_id = await _create_project(client, user["token"], event_bus, "ScForbiddenProject")
        await _add_repo(client, user["token"], project_id)
        resp = await client.get(
            f"/projects/{project_id}/repos/testrepo/status",
            headers=_auth(other["token"]),
        )
        assert resp.status_code == 403
