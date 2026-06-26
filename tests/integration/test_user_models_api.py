"""UserModel API 集成测试（AR-2.3, AR-2.8）

测试 UserModel CRUD + api_key_hash 变更检测 + 被 AgentModelMapping 引用时禁止删除。
"""

import uuid
from typing import Any

import asyncpg
from httpx import AsyncClient


async def _register_and_login(client: AsyncClient, suffix: str = "") -> dict[str, Any]:
    """注册第一个用户（自动 admin）并返回登录响应"""
    username = f"u2_{suffix}_{uuid.uuid4().hex[:6]}"
    await client.post(
        "/auth/register",
        json={"username": username, "password": "pass12345678", "display_name": "Test"},
    )
    resp = await client.post(
        "/auth/login",
        json={"username": username, "password": "pass12345678"},
    )
    assert resp.status_code == 200
    return dict(resp.json())


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_ar_2_3_user_model_crud_and_api_key_hash(client: AsyncClient, db_conn: asyncpg.Connection) -> None:
    """AR-2.3 UserModel CRUD + api_key_hash 变更检测"""
    login = await _register_and_login(client, "23")
    headers = _auth_headers(login["access_token"])
    user_id = login["user_id"]

    # POST 创建 UserModel（api_key="sk-abc"）
    create = await client.post(
        "/users/me/models",
        json={
            "model_id": "我的 GLM-4",
            "provider": "openai_compat",
            "model_name": "glm-4-plus",
            "base_url": "https://open.bigmodel.cn/api/paas/v4",
            "api_key": "sk-abc123def",
        },
        headers=headers,
    )
    assert create.status_code == 201, create.text
    created = create.json()
    assert created["model_id"] == "我的 GLM-4"
    assert "api_key" not in created, "创建响应不应返回明文 api_key"

    # 验证 DB 里 api_key_enc 已加密 + api_key_hash 已存
    row = await db_conn.fetchrow(
        "SELECT api_key_enc, api_key_hash FROM user_models WHERE user_id=$1 AND model_id=$2",
        uuid.UUID(user_id),
        "我的 GLM-4",
    )
    assert row is not None
    enc_1 = bytes(row["api_key_enc"])
    hash_1 = row["api_key_hash"]
    assert enc_1 != b"sk-abc123def", "DB 不应存明文 api_key"
    assert hash_1 != "sk-abc123def", "hash 不应是明文"
    assert len(hash_1) == 64, "SHA-256 hex 应为 64 字符"

    # GET 列表（不返回 api_key，返回 masked "sk-***def"）
    listing = await client.get("/users/me/models", headers=headers)
    assert listing.status_code == 200
    items = listing.json()
    assert len(items) == 1
    assert items[0]["model_id"] == "我的 GLM-4"
    assert "api_key" not in items[0], "GET 列表不应返回明文 api_key"
    masked = items[0].get("api_key_masked", "")
    assert "sk-" in masked, "masked 应含前缀"
    assert "***" in masked, "masked 应含 ***"

    # PUT 更新（不传 api_key）→ api_key_enc 不变（hash 未变）
    update_no_key = await client.put(
        "/users/me/models/我的 GLM-4",
        json={
            "provider": "openai_compat",
            "model_name": "glm-4-plus",
            "base_url": "https://open.bigmodel.cn/api/paas/v4",
        },
        headers=headers,
    )
    assert update_no_key.status_code == 200, update_no_key.text
    row_after = await db_conn.fetchrow(
        "SELECT api_key_enc, api_key_hash FROM user_models WHERE user_id=$1 AND model_id=$2",
        uuid.UUID(user_id),
        "我的 GLM-4",
    )
    assert row_after is not None, "更新后应能查到记录"
    assert bytes(row_after["api_key_enc"]) == enc_1, "未传 api_key 时 api_key_enc 不应变"
    assert row_after["api_key_hash"] == hash_1, "hash 不应变"

    # PUT 更新（传新 api_key="sk-xyz789"）→ api_key_enc 变化（hash 变化触发重新加密）
    update_with_key = await client.put(
        "/users/me/models/我的 GLM-4",
        json={
            "provider": "openai_compat",
            "model_name": "glm-4-plus",
            "base_url": "https://open.bigmodel.cn/api/paas/v4",
            "api_key": "sk-xyz789ghi",
        },
        headers=headers,
    )
    assert update_with_key.status_code == 200
    row_final = await db_conn.fetchrow(
        "SELECT api_key_enc, api_key_hash FROM user_models WHERE user_id=$1 AND model_id=$2",
        uuid.UUID(user_id),
        "我的 GLM-4",
    )
    assert row_final is not None, "更新后应能查到记录"
    assert bytes(row_final["api_key_enc"]) != enc_1, "传新 api_key 时 api_key_enc 应变化"
    assert row_final["api_key_hash"] != hash_1, "hash 应变化"

    # GET 永不返回明文 api_key
    detail = await client.get("/users/me/models/我的 GLM-4", headers=headers)
    assert detail.status_code == 200
    assert "api_key" not in detail.json(), "GET 详情不应返回明文 api_key"


async def test_ar_2_8_user_model_referenced_blocks_delete(client: AsyncClient, db_conn: asyncpg.Connection) -> None:
    """AR-2.8 UserModel 被 AgentModelMapping 引用时禁止删除"""
    login = await _register_and_login(client, "28")
    headers = _auth_headers(login["access_token"])

    # 创建 UserModel "我的 GLM-4"
    create = await client.post(
        "/users/me/models",
        json={
            "model_id": "我的 GLM-4",
            "provider": "openai_compat",
            "model_name": "glm-4-plus",
            "base_url": "https://open.bigmodel.cn/api/paas/v4",
            "api_key": "sk-test123",
        },
        headers=headers,
    )
    assert create.status_code == 201

    # 配置 analyst→"我的 GLM-4"
    mapping = await client.put(
        "/users/me/agent-models",
        json={"analyst": "我的 GLM-4"},
        headers=headers,
    )
    assert mapping.status_code == 200, mapping.text

    # DELETE UserModel → 409
    delete = await client.delete("/users/me/models/我的 GLM-4", headers=headers)
    assert delete.status_code == 409
    assert "analyst" in delete.text, "错误消息应明确被哪个 agent 引用"

    # 解除引用后 DELETE 成功
    clear = await client.put(
        "/users/me/agent-models",
        json={},
        headers=headers,
    )
    assert clear.status_code == 200
    delete_again = await client.delete("/users/me/models/我的 GLM-4", headers=headers)
    assert delete_again.status_code == 204
