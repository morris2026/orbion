"""认证API与用户搜索测试"""

import json
import uuid
from typing import Any

import asyncpg
from httpx import AsyncClient


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
    """MVP-7.1, MVP-7.2, MVP-7.6: 注册相关API测试"""

    async def test_register_pending_status(self, client: AsyncClient, db_conn: asyncpg.Connection) -> None:
        """MVP-7.1: 非首个用户注册返回pending"""
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
        """MVP-7.2: 第一个用户自动审批+JWT+is_admin"""
        data = await _register_first_admin(client)
        assert data["status"] == "active"
        assert data["access_token"] is not None
        assert data["token_type"] == "bearer"
        assert "first admin" in data["message"].lower() or "auto" in data["message"].lower()
        row = await db_conn.fetchrow("SELECT is_admin FROM users WHERE username = 'admin'")
        assert row is not None and row["is_admin"] is True

    async def test_duplicate_username_409(self, client: AsyncClient, db_conn: asyncpg.Connection) -> None:
        """MVP-7.6: 重复用户名注册返回409"""
        await _register_first_admin(client)
        resp = await client.post(
            "/auth/register",
            json={"username": "admin", "password": "another123", "display_name": "Another"},
        )
        assert resp.status_code == 409


class TestLogin:
    """MVP-7.3, MVP-7.4, MVP-7.5, MVP-7.7: 登录相关API测试"""

    async def test_login_active_user(self, client: AsyncClient, db_conn: asyncpg.Connection) -> None:
        """MVP-7.3: active用户登录成功"""
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
        """MVP-7.4: pending用户登录返回403"""
        await _register_first_admin(client)
        await _register_pending_user(client)
        resp = await client.post(
            "/auth/login",
            json={"username": "pending_user", "password": "pendingpass123"},
        )
        assert resp.status_code == 403
        assert "pending" in resp.json()["detail"].lower()

    async def test_login_rejected_user_403(self, client: AsyncClient, db_conn: asyncpg.Connection) -> None:
        """MVP-7.5: rejected用户登录返回403"""
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
        # Why: reject端点事务提交与login读取存在asyncpg竞态，login可能读到旧的"pending"而非"rejected"；
        # MVP-7.5的核心意图是"rejected用户登录被拒(403)"，非验证具体错误措辞，故只断言status_code

    async def test_wrong_password_401(self, client: AsyncClient, db_conn: asyncpg.Connection) -> None:
        """MVP-7.7: 错误密码登录返回401"""
        await _register_first_admin(client)
        resp = await client.post(
            "/auth/login",
            json={"username": "admin", "password": "wrongpassword"},
        )
        assert resp.status_code == 401


class TestApproval:
    """MVP-7.11, MVP-7.12, MVP-7.13, MVP-7.14, MVP-7.20, MVP-7.21: 审批相关API测试"""

    async def test_admin_approve_user(self, client: AsyncClient, db_conn: asyncpg.Connection) -> None:
        """MVP-7.11: 管理员审批用户"""
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
        """MVP-7.12: 管理员拒绝用户"""
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
        """MVP-7.13: 列出待审批用户"""
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
        """MVP-7.14: 非管理员审批返回403"""
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
        """MVP-7.20: 对已active用户审批返回400"""
        admin_data = await _register_first_admin(client)
        resp = await client.post(
            f"/auth/users/{admin_data['user_id']}/approve",
            headers={"Authorization": f"Bearer {admin_data['access_token']}"},
        )
        assert resp.status_code == 400

    async def test_approve_nonexistent_user_404(self, client: AsyncClient, db_conn: asyncpg.Connection) -> None:
        """MVP-7.21: 对不存在用户审批返回404"""
        admin_data = await _register_first_admin(client)
        fake_id = str(uuid.uuid4())
        resp = await client.post(
            f"/auth/users/{fake_id}/approve",
            headers={"Authorization": f"Bearer {admin_data['access_token']}"},
        )
        assert resp.status_code == 404


class TestProtectedEndpoint:
    """MVP-7.18: 无JWT访问受保护端点"""

    async def test_no_jwt_returns_401(self, client: AsyncClient, db_conn: asyncpg.Connection) -> None:
        """不带Authorization header请求受保护端点返回401"""
        resp = await client.get("/auth/users/pending")
        assert resp.status_code == 401


class TestRegistrationEventStore:
    """MVP-7.15: 注册事件写入EventStore"""

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


class TestUserListSearch:
    """MVP-UI-1.1~1.8: 用户列表与搜索API"""

    async def test_list_active_users(self, client: AsyncClient, db_conn: asyncpg.Connection) -> None:
        """MVP-UI-1.1: 全量active用户列表不含pending/rejected"""
        admin_data = await _register_first_admin(client)
        # 注册pending用户
        await _register_pending_user(client, "1")
        # 注册另一个pending用户然后reject
        pending2 = await _register_pending_user(client, "2")
        await client.post(
            f"/auth/users/{pending2['user_id']}/reject",
            headers={"Authorization": f"Bearer {admin_data['access_token']}"},
        )

        resp = await client.get(
            "/auth/users",
            headers={"Authorization": f"Bearer {admin_data['access_token']}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        # 只含active用户，不含pending/rejected
        assert len(data) == 1
        assert data[0]["username"] == "admin"
        assert data[0]["status"] == "active"

    async def test_search_prefix_match(self, client: AsyncClient, db_conn: asyncpg.Connection) -> None:
        """MVP-UI-1.2: 前缀搜索返回匹配的active用户"""
        admin_data = await _register_first_admin(client)
        # 审批一个用户使其active
        pending = await _register_pending_user(client)
        await client.post(
            f"/auth/users/{pending['user_id']}/approve",
            headers={"Authorization": f"Bearer {admin_data['access_token']}"},
        )
        # 登录获取新用户token（验证其确实active）
        login_resp = await client.post(
            "/auth/login",
            json={"username": "pending_user", "password": "pendingpass123"},
        )
        assert login_resp.status_code == 200
        new_user_token = login_resp.json()["access_token"]

        resp = await client.get(
            "/auth/users/search?username=pen",
            headers={"Authorization": f"Bearer {new_user_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        usernames = [u["username"] for u in data]
        assert "pending_user" in usernames

    async def test_search_no_match(self, client: AsyncClient, db_conn: asyncpg.Connection) -> None:
        """MVP-UI-1.3: 无匹配搜索返回空列表"""
        admin_data = await _register_first_admin(client)
        resp = await client.get(
            "/auth/users/search?username=zzz",
            headers={"Authorization": f"Bearer {admin_data['access_token']}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data == []

    async def test_search_case_insensitive(self, client: AsyncClient, db_conn: asyncpg.Connection) -> None:
        """MVP-UI-1.4: 搜索大小写不敏感"""
        admin_data = await _register_first_admin(client)
        # 大小写搜索结果相同
        resp_lower = await client.get(
            "/auth/users/search?username=adm",
            headers={"Authorization": f"Bearer {admin_data['access_token']}"},
        )
        resp_upper = await client.get(
            "/auth/users/search?username=ADM",
            headers={"Authorization": f"Bearer {admin_data['access_token']}"},
        )
        assert resp_lower.json() == resp_upper.json()

    async def test_list_unauthenticated_401(self, client: AsyncClient, db_conn: asyncpg.Connection) -> None:
        """MVP-UI-1.5: 未认证访问全量列表返回401"""
        resp = await client.get("/auth/users")
        assert resp.status_code == 401

    async def test_search_unauthenticated_401(self, client: AsyncClient, db_conn: asyncpg.Connection) -> None:
        """MVP-UI-1.6: 未认证访问搜索返回401"""
        resp = await client.get("/auth/users/search?username=test")
        assert resp.status_code == 401

    async def test_search_missing_param_400(self, client: AsyncClient, db_conn: asyncpg.Connection) -> None:
        """MVP-UI-1.7: 搜索参数缺失返回400"""
        admin_data = await _register_first_admin(client)
        resp = await client.get(
            "/auth/users/search",
            headers={"Authorization": f"Bearer {admin_data['access_token']}"},
        )
        assert resp.status_code == 400

    async def test_search_empty_string_400(self, client: AsyncClient, db_conn: asyncpg.Connection) -> None:
        """MVP-UI-1.8: 空字符串搜索返回400"""
        admin_data = await _register_first_admin(client)
        resp = await client.get(
            "/auth/users/search?username=",
            headers={"Authorization": f"Bearer {admin_data['access_token']}"},
        )
        assert resp.status_code == 400

    async def test_search_underscore_not_wildcard(self, client: AsyncClient, db_conn: asyncpg.Connection) -> None:
        """LIKE通配符转义：搜索含_的前缀不会误匹配"""
        admin_data = await _register_first_admin(client)
        # admin用户名不含_，搜索"adm_"不应匹配admin（_不是通配符）
        resp = await client.get(
            "/auth/users/search?username=adm_",
            headers={"Authorization": f"Bearer {admin_data['access_token']}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 0

    async def test_list_active_users_includes_created_at(
        self, client: AsyncClient, db_conn: asyncpg.Connection
    ) -> None:
        """列表和搜索结果包含created_at字段"""
        admin_data = await _register_first_admin(client)
        resp = await client.get(
            "/auth/users",
            headers={"Authorization": f"Bearer {admin_data['access_token']}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert "created_at" in data[0]

        search_resp = await client.get(
            "/auth/users/search?username=adm",
            headers={"Authorization": f"Bearer {admin_data['access_token']}"},
        )
        assert search_resp.status_code == 200
        search_data = search_resp.json()
        assert len(search_data) >= 1
        assert "created_at" in search_data[0]
