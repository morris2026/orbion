"""步骤7认证API测试：注册、登录、审批端点"""

import json
import uuid
from collections.abc import AsyncGenerator
from typing import Any

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient

from app.config import get_settings
from app.hub.auth.repository import load_user_repo_impl
from app.hub.events.bus import InProcessEventBus
from app.hub.events.store import load_store_impl
from app.main import app

settings = get_settings()


@pytest.fixture
async def db_conn() -> AsyncGenerator[asyncpg.Connection, None]:
    """每个测试独立的DB连接，测试后清理users表"""
    conn = await asyncpg.connect(settings.postgres.url)
    # 清理users表和关联的event_log记录
    await conn.execute("DELETE FROM event_log WHERE event_type = 'UserRegistered'")
    await conn.execute("DELETE FROM users")
    yield conn
    await conn.execute("DELETE FROM event_log WHERE event_type = 'UserRegistered'")
    await conn.execute("DELETE FROM users")
    await conn.close()


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """httpx AsyncClient，初始化app.state（pool/event_store/event_bus）"""
    pool = await asyncpg.create_pool(settings.postgres.url, min_size=2, max_size=5)
    app.state.pool = pool

    store_cls = load_store_impl("postgres")
    event_store = store_cls()
    await event_store.connect()
    app.state.event_store = event_store
    app.state.event_bus = InProcessEventBus()
    app.state.user_repo_cls = load_user_repo_impl("postgres")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    await event_store.close()
    await pool.close()


async def _register_first_admin(client: AsyncClient) -> dict[str, Any]:
    """注册第一个用户（自动审批为admin），返回完整响应"""
    resp = await client.post(
        "/auth/register",
        json={
            "username": "admin",
            "password": "adminpass123",
            "display_name": "Admin User",
        },
    )
    assert resp.status_code == 200
    return dict(resp.json())


async def _register_pending_user(client: AsyncClient, suffix: str = "") -> dict[str, Any]:
    """注册一个pending用户，返回完整响应"""
    resp = await client.post(
        "/auth/register",
        json={
            "username": f"pending_user{suffix}",
            "password": "pendingpass123",
            "display_name": f"Pending User{suffix}",
        },
    )
    assert resp.status_code == 200
    return dict(resp.json())


class TestRegistration:
    """TC-7.1, TC-7.2, TC-7.6: 注册相关API测试"""

    async def test_register_pending_status(self, client: AsyncClient, db_conn: asyncpg.Connection) -> None:
        """TC-7.1: 非首个用户注册返回pending"""
        await _register_first_admin(client)
        resp = await client.post(
            "/auth/register",
            json={"username": "normal", "password": "normalpass123", "display_name": "Normal"},
        )
        data = resp.json()
        assert data["status"] == "pending"
        assert data["message"] != ""
        assert "access_token" not in data or data["access_token"] is None

    async def test_first_user_auto_approved(self, client: AsyncClient, db_conn: asyncpg.Connection) -> None:
        """TC-7.2: 第一个用户自动审批+JWT+is_admin"""
        data = await _register_first_admin(client)
        assert data["status"] == "active"
        assert data["access_token"] is not None
        assert data["token_type"] == "bearer"
        assert "first admin" in data["message"].lower() or "auto" in data["message"].lower()
        row = await db_conn.fetchrow("SELECT is_admin FROM users WHERE username = 'admin'")
        assert row is not None and row["is_admin"] is True

    async def test_duplicate_username_409(self, client: AsyncClient, db_conn: asyncpg.Connection) -> None:
        """TC-7.6: 重复用户名注册返回409"""
        await _register_first_admin(client)
        resp = await client.post(
            "/auth/register",
            json={"username": "admin", "password": "another123", "display_name": "Another"},
        )
        assert resp.status_code == 409


class TestLogin:
    """TC-7.3, TC-7.4, TC-7.5, TC-7.7: 登录相关API测试"""

    async def test_login_active_user(self, client: AsyncClient, db_conn: asyncpg.Connection) -> None:
        """TC-7.3: active用户登录成功"""
        await _register_first_admin(client)
        resp = await client.post(
            "/auth/login",
            json={"username": "admin", "password": "adminpass123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["access_token"] is not None
        assert data["token_type"] == "bearer"

    async def test_login_pending_user_403(self, client: AsyncClient, db_conn: asyncpg.Connection) -> None:
        """TC-7.4: pending用户登录返回403"""
        await _register_first_admin(client)
        await _register_pending_user(client)
        resp = await client.post(
            "/auth/login",
            json={"username": "pending_user", "password": "pendingpass123"},
        )
        assert resp.status_code == 403
        assert "pending" in resp.json()["detail"].lower()

    async def test_login_rejected_user_403(self, client: AsyncClient, db_conn: asyncpg.Connection) -> None:
        """TC-7.5: rejected用户登录返回403"""
        admin_data = await _register_first_admin(client)
        pending_data = await _register_pending_user(client)
        await client.post(
            f"/auth/users/{pending_data['user_id']}/reject",
            headers={"Authorization": f"Bearer {admin_data['access_token']}"},
        )
        resp = await client.post(
            "/auth/login",
            json={"username": "pending_user", "password": "pendingpass123"},
        )
        assert resp.status_code == 403
        assert "rejected" in resp.json()["detail"].lower()

    async def test_wrong_password_401(self, client: AsyncClient, db_conn: asyncpg.Connection) -> None:
        """TC-7.7: 错误密码登录返回401"""
        await _register_first_admin(client)
        resp = await client.post(
            "/auth/login",
            json={"username": "admin", "password": "wrongpassword"},
        )
        assert resp.status_code == 401


class TestApproval:
    """TC-7.11, TC-7.12, TC-7.13, TC-7.14, TC-7.20, TC-7.21: 审批相关API测试"""

    async def test_admin_approve_user(self, client: AsyncClient, db_conn: asyncpg.Connection) -> None:
        """TC-7.11: 管理员审批用户"""
        admin_data = await _register_first_admin(client)
        pending_data = await _register_pending_user(client)
        resp = await client.post(
            f"/auth/users/{pending_data['user_id']}/approve",
            headers={"Authorization": f"Bearer {admin_data['access_token']}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "active"
        login_resp = await client.post(
            "/auth/login",
            json={"username": "pending_user", "password": "pendingpass123"},
        )
        assert login_resp.status_code == 200

    async def test_admin_reject_user(self, client: AsyncClient, db_conn: asyncpg.Connection) -> None:
        """TC-7.12: 管理员拒绝用户"""
        admin_data = await _register_first_admin(client)
        pending_data = await _register_pending_user(client)
        resp = await client.post(
            f"/auth/users/{pending_data['user_id']}/reject",
            json={"reason": "不符合要求"},
            headers={"Authorization": f"Bearer {admin_data['access_token']}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "rejected"
        assert data["reason"] == "不符合要求"

    async def test_list_pending_users(self, client: AsyncClient, db_conn: asyncpg.Connection) -> None:
        """TC-7.13: 列出待审批用户"""
        admin_data = await _register_first_admin(client)
        await _register_pending_user(client, "1")
        await _register_pending_user(client, "2")
        resp = await client.get(
            "/auth/users/pending",
            headers={"Authorization": f"Bearer {admin_data['access_token']}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

    async def test_non_admin_approve_403(self, client: AsyncClient, db_conn: asyncpg.Connection) -> None:
        """TC-7.14: 非管理员审批返回403"""
        admin_data = await _register_first_admin(client)
        pending = await _register_pending_user(client)
        await client.post(
            f"/auth/users/{pending['user_id']}/approve",
            headers={"Authorization": f"Bearer {admin_data['access_token']}"},
        )
        login = await client.post(
            "/auth/login",
            json={"username": "pending_user", "password": "pendingpass123"},
        )
        non_admin_token = login.json()["access_token"]
        another = await _register_pending_user(client, "2")
        resp = await client.post(
            f"/auth/users/{another['user_id']}/approve",
            headers={"Authorization": f"Bearer {non_admin_token}"},
        )
        assert resp.status_code == 403

    async def test_approve_already_active_400(self, client: AsyncClient, db_conn: asyncpg.Connection) -> None:
        """TC-7.20: 对已active用户审批返回400"""
        admin_data = await _register_first_admin(client)
        resp = await client.post(
            f"/auth/users/{admin_data['user_id']}/approve",
            headers={"Authorization": f"Bearer {admin_data['access_token']}"},
        )
        assert resp.status_code == 400

    async def test_approve_nonexistent_user_404(self, client: AsyncClient, db_conn: asyncpg.Connection) -> None:
        """TC-7.21: 对不存在用户审批返回404"""
        admin_data = await _register_first_admin(client)
        fake_id = str(uuid.uuid4())
        resp = await client.post(
            f"/auth/users/{fake_id}/approve",
            headers={"Authorization": f"Bearer {admin_data['access_token']}"},
        )
        assert resp.status_code == 404


class TestProtectedEndpoint:
    """TC-7.18: 无JWT访问受保护端点"""

    async def test_no_jwt_returns_401(self, client: AsyncClient, db_conn: asyncpg.Connection) -> None:
        """不带Authorization header请求受保护端点返回401"""
        resp = await client.get("/auth/users/pending")
        assert resp.status_code == 401


class TestRegistrationEventStore:
    """TC-7.15: 注册事件写入EventStore"""

    async def test_registration_event_in_event_store(self, client: AsyncClient, db_conn: asyncpg.Connection) -> None:
        """注册后EventStore有UserRegistered事件"""
        reg = await _register_first_admin(client)
        rows = await db_conn.fetch(
            "SELECT * FROM event_log WHERE event_type = 'UserRegistered' AND participant_id = $1",
            reg["user_id"],
        )
        assert len(rows) == 1
        event = rows[0]
        assert event["participant_type"] == "human"
        assert event["project_id"] == ""  # 平台级事件
        payload = event["payload"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        assert payload["username"] == "admin"
        assert payload["status"] == "active"
        assert payload["is_admin"] is True
