"""仓库系统消息集成测试 — add_repo 产生 system 类型的 DiscussionMessageCreated 事件"""

import uuid

import asyncpg
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


async def _create_project(
    client: AsyncClient, token: str, event_bus: InProcessEventBus, name: str = "SysMsgTestProject"
) -> dict[str, str]:
    resp = await client.post("/projects", json={"name": name}, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    await event_bus.wait_for_pending()
    data = resp.json()
    return {"id": str(data["id"]), "default_thread_id": str(data.get("default_thread_id", ""))}


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class TestRepoSystemMessages:
    """add_repo 产生 system 消息：init 成功、clone 失败、字段验证"""

    async def test_init_repo_sends_system_messages(
        self,
        client: AsyncClient,
        db_conn: asyncpg.Connection,
        event_bus: InProcessEventBus,
        user_repo_provider: UserRepositoryProvider,
    ) -> None:
        """git init 成功→默认线程出现两条 system 消息（正在初始化 + 已初始化）"""
        user = await _create_user(user_repo_provider, "sysmsg_init_user")
        project = await _create_project(client, user["token"], event_bus, "SysMsgInitProject")
        project_id, thread_id = project["id"], project["default_thread_id"]

        resp = await client.post(
            f"/projects/{project_id}/repos",
            json={"name": "init-repo"},
            headers=_auth(user["token"]),
        )
        assert resp.status_code == 201
        await event_bus.wait_for_pending()

        # 查询默认线程中的 system 消息
        rows = await db_conn.fetch(
            "SELECT content, participant_type, participant_id "
            "FROM thread_messages WHERE thread_id = $1 AND participant_type = 'system' "
            "ORDER BY created_at",
            uuid.UUID(thread_id),
        )
        assert len(rows) == 2
        assert "正在初始化" in rows[0]["content"]
        assert "init-repo" in rows[0]["content"]
        assert "已初始化" in rows[1]["content"]
        assert "init-repo" in rows[1]["content"]
        for row in rows:
            assert row["participant_type"] == "system"
            assert row["participant_id"] == "system"

    async def test_clone_failure_sends_system_messages(
        self,
        client: AsyncClient,
        db_conn: asyncpg.Connection,
        event_bus: InProcessEventBus,
        user_repo_provider: UserRepositoryProvider,
    ) -> None:
        """clone 失败→默认线程出现两条 system 消息（正在克隆 + 克隆失败），API 返回 400"""
        user = await _create_user(user_repo_provider, "sysmsg_clone_fail")
        project = await _create_project(client, user["token"], event_bus, "SysMsgCloneFailProject")
        project_id, thread_id = project["id"], project["default_thread_id"]

        # 使用无效 URL 触发 clone 失败
        resp = await client.post(
            f"/projects/{project_id}/repos",
            json={"url": "https://invalid.host.example/nonexistent.git", "name": "fail-repo"},
            headers=_auth(user["token"]),
        )
        # clone 失败 → 路由返回 400
        assert resp.status_code == 400
        await event_bus.wait_for_pending()

        rows = await db_conn.fetch(
            "SELECT content, participant_type FROM thread_messages "
            "WHERE thread_id = $1 AND participant_type = 'system' ORDER BY created_at",
            uuid.UUID(thread_id),
        )
        assert len(rows) == 2
        assert "正在克隆" in rows[0]["content"]
        assert "克隆失败" in rows[1]["content"]

    async def test_system_messages_appear_in_messages_api(
        self,
        client: AsyncClient,
        event_bus: InProcessEventBus,
        user_repo_provider: UserRepositoryProvider,
    ) -> None:
        """system 消息可通过消息列表 API 查询到"""
        user = await _create_user(user_repo_provider, "sysmsg_api_user")
        project = await _create_project(client, user["token"], event_bus, "SysMsgApiProject")
        project_id, thread_id = project["id"], project["default_thread_id"]

        await client.post(
            f"/projects/{project_id}/repos",
            json={"name": "api-repo"},
            headers=_auth(user["token"]),
        )
        await event_bus.wait_for_pending()

        resp = await client.get(
            f"/threads/{thread_id}/messages",
            headers=_auth(user["token"]),
        )
        assert resp.status_code == 200
        messages = resp.json()
        system_msgs = [m for m in messages if m["participant_type"] == "system"]
        assert len(system_msgs) == 2
        assert any("正在初始化" in m["content"] for m in system_msgs)
        assert any("已初始化" in m["content"] for m in system_msgs)
        for msg in system_msgs:
            assert msg["participant_id"] == "system"
            assert msg["display_name"] == "系统"

    async def test_system_messages_in_event_log(
        self,
        client: AsyncClient,
        db_conn: asyncpg.Connection,
        event_bus: InProcessEventBus,
        user_repo_provider: UserRepositoryProvider,
    ) -> None:
        """system 消息在 event_log 中有对应的 DiscussionMessageCreated 事件"""
        user = await _create_user(user_repo_provider, "sysmsg_event_user")
        project = await _create_project(client, user["token"], event_bus, "SysMsgEventProject")
        project_id = project["id"]

        await client.post(
            f"/projects/{project_id}/repos",
            json={"name": "event-repo"},
            headers=_auth(user["token"]),
        )
        await event_bus.wait_for_pending()

        rows = await db_conn.fetch(
            "SELECT participant_type, participant_id, payload FROM event_log "
            "WHERE project_id = $1 AND event_type = 'DiscussionMessageCreated' AND participant_type = 'system'",
            project_id,
        )
        assert len(rows) >= 2
        for row in rows:
            assert row["participant_type"] == "system"
            assert row["participant_id"] == "system"
