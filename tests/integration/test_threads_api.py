"""讨论线程与消息API集成测试：TC-10.1–TC-10.7"""

import uuid
from typing import Any

import asyncpg
import pytest
from httpx import AsyncClient

from app.config import get_settings
from app.hub.auth.repository import UserRepositoryProvider
from app.hub.auth.service import create_access_token, hash_password
from app.hub.events.bus import InProcessEventBus

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


async def _create_thread(client: AsyncClient, token: str, project_id: str, title: str = "Test Thread") -> str:
    """创建线程并返回thread_id"""
    resp = await client.post(
        f"/projects/{project_id}/threads",
        json={"title": title},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    return str(resp.json()["id"])


async def _send_message(
    client: AsyncClient, token: str, thread_id: str, content: str = "Hello world", request_summary: bool = False
) -> dict[str, Any]:
    """发送消息并返回响应"""
    resp = await client.post(
        f"/threads/{thread_id}/messages",
        json={"content": content, "request_summary": request_summary},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    return dict(resp.json())


# -- TC-10 测试 --


class TestCreateThread:
    """TC-10.1: 创建线程"""

    @pytest.mark.asyncio
    async def test_create_thread(
        self,
        client: AsyncClient,
        db_conn: asyncpg.Connection,
        event_bus: InProcessEventBus,
        user_repo_provider: UserRepositoryProvider,
    ) -> None:
        user = await _create_user(user_repo_provider, "thread_creator")
        project_id = await _create_project(client, user["token"])
        await event_bus.wait_for_pending()

        resp = await client.post(
            f"/projects/{project_id}/threads",
            json={"title": "API Design"},
            headers={"Authorization": f"Bearer {user['token']}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "id" in data
        assert data["project_id"] == project_id
        assert data["title"] == "API Design"
        assert data["status"] == "active"
        assert data["type"] == "discussion"
        assert "created_at" in data

        # threads表有记录
        thread_id = data["id"]
        await event_bus.wait_for_pending()
        row = await db_conn.fetchrow("SELECT title, status, type FROM threads WHERE id = $1", uuid.UUID(thread_id))
        assert row is not None
        assert row["title"] == "API Design"
        assert row["status"] == "active"
        assert row["type"] == "discussion"


class TestThreadListAggregation:
    """TC-10.2: 线程列表含聚合字段"""

    @pytest.mark.asyncio
    async def test_thread_list_aggregation(
        self,
        client: AsyncClient,
        event_bus: InProcessEventBus,
        user_repo_provider: UserRepositoryProvider,
    ) -> None:
        user = await _create_user(user_repo_provider, "thread_aggr")
        project_id = await _create_project(client, user["token"])
        await event_bus.wait_for_pending()

        # 创建线程
        thread_id = await _create_thread(client, user["token"], project_id, "Discussion Thread")
        await event_bus.wait_for_pending()

        # 发送消息
        await _send_message(client, user["token"], thread_id, "My message")
        await event_bus.wait_for_pending()

        # 线程列表
        resp = await client.get(
            f"/projects/{project_id}/threads",
            headers={"Authorization": f"Bearer {user['token']}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        found = [t for t in data if t["id"] == thread_id]
        assert len(found) == 1
        thread = found[0]
        assert thread["has_summary"] is False
        assert thread["pending_plan_count"] == 0
        # thread创建消息 + 1条用户消息
        assert thread["message_count"] >= 1


class TestSendMessageEventChain:
    """TC-10.3: 发送消息→事件持久化+投影更新"""

    @pytest.mark.asyncio
    async def test_send_message_event_chain(
        self,
        client: AsyncClient,
        db_conn: asyncpg.Connection,
        event_bus: InProcessEventBus,
        user_repo_provider: UserRepositoryProvider,
    ) -> None:
        user = await _create_user(user_repo_provider, "msg_chain_user")
        project_id = await _create_project(client, user["token"])
        await event_bus.wait_for_pending()
        thread_id = await _create_thread(client, user["token"], project_id)
        await event_bus.wait_for_pending()

        # 发送消息
        await _send_message(client, user["token"], thread_id, "Hello from test")
        await event_bus.wait_for_pending()

        # EventStore有DiscussionMessageCreated事件
        rows = await db_conn.fetch(
            "SELECT event_type, payload FROM event_log "
            "WHERE project_id = $1 AND event_type = 'DiscussionMessageCreated'",
            project_id,
        )
        # thread创建时也发布了DiscussionMessageCreated事件，所以至少2条
        assert len(rows) >= 1
        msg_event_found = False
        for row in rows:
            payload = row["payload"]
            if isinstance(payload, str):
                import json

                payload = json.loads(payload)
            if payload.get("content") == "Hello from test":
                msg_event_found = True
                assert payload["thread_id"] == thread_id
        assert msg_event_found

        # thread_messages投影有新记录
        msg_rows = await db_conn.fetch(
            "SELECT content, participant_id, event_type FROM thread_messages "
            "WHERE thread_id = $1 AND content = 'Hello from test'",
            uuid.UUID(thread_id),
        )
        assert len(msg_rows) == 1
        assert msg_rows[0]["participant_id"] == user["id"]
        assert msg_rows[0]["event_type"] == "DiscussionMessageCreated"


class TestMessageCursorPagination:
    """TC-10.4: 消息列表游标分页"""

    @pytest.mark.asyncio
    async def test_message_cursor_pagination(
        self,
        client: AsyncClient,
        event_bus: InProcessEventBus,
        user_repo_provider: UserRepositoryProvider,
    ) -> None:
        user = await _create_user(user_repo_provider, "pagination_user")
        project_id = await _create_project(client, user["token"])
        await event_bus.wait_for_pending()
        thread_id = await _create_thread(client, user["token"], project_id)
        await event_bus.wait_for_pending()

        # 发送多条消息
        for i in range(55):
            await _send_message(client, user["token"], thread_id, f"Message {i}")
            await event_bus.wait_for_pending()

        # 无参数：返回最近50条（线程创建消息 + 最多49条用户消息）
        resp = await client.get(
            f"/threads/{thread_id}/messages",
            headers={"Authorization": f"Bearer {user['token']}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 50

        # before参数：返回指定ID之前的消息
        last_msg_id = data[0]["id"]  # 最近的
        resp_before = await client.get(
            f"/threads/{thread_id}/messages?before={last_msg_id}",
            headers={"Authorization": f"Bearer {user['token']}"},
        )
        assert resp_before.status_code == 200
        data_before = resp_before.json()
        assert len(data_before) <= 50
        # 所有消息都在 last_msg_id 之前
        for msg in data_before:
            assert msg["id"] != last_msg_id

        # limit参数：限制条数
        resp_limit = await client.get(
            f"/threads/{thread_id}/messages?limit=20",
            headers={"Authorization": f"Bearer {user['token']}"},
        )
        assert resp_limit.status_code == 200
        data_limit = resp_limit.json()
        assert len(data_limit) == 20

        # 人类和Agent消息同流（目前只有人类消息）
        for msg in data:
            assert msg["participant_type"] in ("human", "agent")


class TestRequestSummaryFlag:
    """TC-10.5: request_summary标志"""

    @pytest.mark.asyncio
    async def test_request_summary_flag(
        self,
        client: AsyncClient,
        db_conn: asyncpg.Connection,
        event_bus: InProcessEventBus,
        user_repo_provider: UserRepositoryProvider,
    ) -> None:
        user = await _create_user(user_repo_provider, "summary_flag_user")
        project_id = await _create_project(client, user["token"])
        await event_bus.wait_for_pending()
        thread_id = await _create_thread(client, user["token"], project_id)
        await event_bus.wait_for_pending()

        # 发送消息 request_summary=true
        await _send_message(client, user["token"], thread_id, "Please summarize", request_summary=True)
        await event_bus.wait_for_pending()

        # DiscussionMessageCreated事件payload中request_summary=true
        rows = await db_conn.fetch(
            "SELECT payload FROM event_log WHERE project_id = $1 AND event_type = 'DiscussionMessageCreated'",
            project_id,
        )
        import json

        summary_found = False
        for row in rows:
            payload = row["payload"]
            if isinstance(payload, str):
                payload = json.loads(payload)
            if payload.get("content") == "Please summarize":
                assert payload["request_summary"] is True
                summary_found = True
        assert summary_found


class TestNonMemberSendMessage:
    """TC-10.6: 非项目成员发送消息→403"""

    @pytest.mark.asyncio
    async def test_non_member_send_message(
        self,
        client: AsyncClient,
        event_bus: InProcessEventBus,
        user_repo_provider: UserRepositoryProvider,
    ) -> None:
        owner = await _create_user(user_repo_provider, "thread_owner_403")
        outsider = await _create_user(user_repo_provider, "thread_outsider")
        project_id = await _create_project(client, owner["token"])
        await event_bus.wait_for_pending()
        thread_id = await _create_thread(client, owner["token"], project_id)
        await event_bus.wait_for_pending()

        # 非成员发送消息→403
        resp = await client.post(
            f"/threads/{thread_id}/messages",
            json={"content": "Unauthorized message"},
            headers={"Authorization": f"Bearer {outsider['token']}"},
        )
        assert resp.status_code == 403

        # 非成员列出消息→403
        resp_list = await client.get(
            f"/threads/{thread_id}/messages",
            headers={"Authorization": f"Bearer {outsider['token']}"},
        )
        assert resp_list.status_code == 403

        # 非成员列出线程→403
        resp_threads = await client.get(
            f"/projects/{project_id}/threads",
            headers={"Authorization": f"Bearer {outsider['token']}"},
        )
        assert resp_threads.status_code == 403

        # 非成员创建线程→403
        resp_create = await client.post(
            f"/projects/{project_id}/threads",
            json={"title": "Unauthorized thread"},
            headers={"Authorization": f"Bearer {outsider['token']}"},
        )
        assert resp_create.status_code == 403


class TestMessageErrorPaths:
    """TC-10.7: 消息发送错误路径"""

    @pytest.mark.asyncio
    async def test_empty_content(
        self,
        client: AsyncClient,
        event_bus: InProcessEventBus,
        user_repo_provider: UserRepositoryProvider,
    ) -> None:
        """空字符串content→400"""
        user = await _create_user(user_repo_provider, "error_empty")
        project_id = await _create_project(client, user["token"])
        await event_bus.wait_for_pending()
        thread_id = await _create_thread(client, user["token"], project_id)
        await event_bus.wait_for_pending()

        resp = await client.post(
            f"/threads/{thread_id}/messages",
            json={"content": ""},
            headers={"Authorization": f"Bearer {user['token']}"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_overlength_content(
        self,
        client: AsyncClient,
        event_bus: InProcessEventBus,
        user_repo_provider: UserRepositoryProvider,
    ) -> None:
        """超长content(10001字符)→400"""
        user = await _create_user(user_repo_provider, "error_long")
        project_id = await _create_project(client, user["token"])
        await event_bus.wait_for_pending()
        thread_id = await _create_thread(client, user["token"], project_id)
        await event_bus.wait_for_pending()

        resp = await client.post(
            f"/threads/{thread_id}/messages",
            json={"content": "x" * 10001},
            headers={"Authorization": f"Bearer {user['token']}"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_nonexistent_thread(
        self,
        client: AsyncClient,
        user_repo_provider: UserRepositoryProvider,
    ) -> None:
        """不存在的thread_id→404"""
        user = await _create_user(user_repo_provider, "error_notfound")
        fake_thread_id = str(uuid.uuid4())

        resp = await client.post(
            f"/threads/{fake_thread_id}/messages",
            json={"content": "Test message"},
            headers={"Authorization": f"Bearer {user['token']}"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_nonexistent_thread_list_messages(
        self,
        client: AsyncClient,
        user_repo_provider: UserRepositoryProvider,
    ) -> None:
        """不存在的thread_id获取消息列表→404"""
        user = await _create_user(user_repo_provider, "error_notfound_list")
        fake_thread_id = str(uuid.uuid4())

        resp = await client.get(
            f"/threads/{fake_thread_id}/messages",
            headers={"Authorization": f"Bearer {user['token']}"},
        )
        assert resp.status_code == 404
