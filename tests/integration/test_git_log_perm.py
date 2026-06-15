"""git-log 权限码修复测试 — 非成员应返回 403（当前返回 404）"""

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
    client: AsyncClient, token: str, event_bus: InProcessEventBus, name: str = "GitLogPermProject"
) -> str:
    resp = await client.post("/projects", json={"name": name}, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    await event_bus.wait_for_pending()
    return str(resp.json()["id"])


class TestGitLogPermission:
    async def test_non_member_returns_403(
        self, client: AsyncClient, user_repo_provider: UserRepositoryProvider, event_bus: InProcessEventBus
    ) -> None:
        """非项目成员访问 git-log 应返回 403（与其他端点一致）"""
        user = await _create_user(user_repo_provider, "gluser1")
        other = await _create_user(user_repo_provider, "gluser2")
        project_id = await _create_project(client, user["token"], event_bus, "GitLogPermProject")
        resp = await client.get(
            f"/git/{project_id}/git-log",
            params={"repo_name": "testrepo"},
            headers={"Authorization": f"Bearer {other['token']}"},
        )
        assert resp.status_code == 403
