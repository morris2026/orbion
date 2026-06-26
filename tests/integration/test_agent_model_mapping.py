"""AgentModelMapping 四级解析测试（AR-2.4, AR-2.5, AR-2.6）

测试解析顺序：项目级覆盖 > 用户级 agent_models.enc > 智能默认单 UserModel > 引导配置
"""

import uuid
from typing import Any

from httpx import AsyncClient

from app.biz.agent_models.service import AgentModelMappingService
from app.biz.agent_models.store import AgentModelStore
from app.biz.user_models.service import UserModelService


async def _register_and_login(client: AsyncClient, suffix: str = "") -> dict[str, Any]:
    username = f"u4_{suffix}_{uuid.uuid4().hex[:6]}"
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


async def _create_model(client: AsyncClient, headers: dict[str, str], model_id: str) -> None:
    resp = await client.post(
        "/users/me/models",
        json={
            "model_id": model_id,
            "provider": "openai_compat",
            "model_name": "glm-4-plus",
            "base_url": "https://open.bigmodel.cn/api/paas/v4",
            "api_key": f"sk-{model_id}",
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text


async def test_ar_2_4_agent_model_mapping_four_level_resolution(client: AsyncClient) -> None:
    """AR-2.4 AgentModelMapping 四级解析顺序"""
    login = await _register_and_login(client, "24")
    headers = _auth_headers(login["access_token"])
    user_id = login["user_id"]

    # 创建 2 个 UserModel
    await _create_model(client, headers, "GLM-4")
    await _create_model(client, headers, "Claude")

    # 直接通过 service 测试四级解析（API 层在步骤 5 dispatch 时才用）
    from app.config import get_settings

    settings = get_settings()
    import asyncpg

    pool = await asyncpg.create_pool(settings.postgres.url, min_size=1, max_size=5)
    try:
        um_service = UserModelService(pool)
        store = AgentModelStore(settings.root_dir)
        service = AgentModelMappingService(store, um_service, settings.projects_dir)

        # 用户级配置 analyst→GLM-4
        await service.set_user_mapping(user_id, {"analyst": "GLM-4"})

        # 1. 有用户级 → 返回用户级（GLM-4）
        model_id = await service.resolve_model_id(user_id, "analyst")
        assert model_id == "GLM-4", "有用户级时应返回用户级"

        # 2. 项目级 override 配置 analyst→Claude → 返回项目级（Claude）
        project_id = str(uuid.uuid4())
        service.set_project_override(project_id, {"analyst": "Claude"})
        model_id = await service.resolve_model_id(user_id, "analyst", project_id=project_id)
        assert model_id == "Claude", "有项目级覆盖时应返回项目级"

        # 3. 项目级 override 删除后 → 回退到用户级（GLM-4）
        service.delete_project_override(project_id, "analyst")
        model_id = await service.resolve_model_id(user_id, "analyst", project_id=project_id)
        assert model_id == "GLM-4", "无项目级覆盖时回退到用户级"

        # 4. 用户级也未配 + 多 UserModel → 抛 ModelNotConfiguredError
        await service.set_user_mapping(user_id, {})  # 清空用户级
        from app.biz.agent_models.service import ModelNotConfiguredError

        with __import__("pytest").raises(ModelNotConfiguredError):
            await service.resolve_model_id(user_id, "analyst", project_id=project_id)
    finally:
        await pool.close()


async def test_ar_2_5_single_user_model_smart_default(client: AsyncClient) -> None:
    """AR-2.5 单 UserModel 智能默认"""
    login = await _register_and_login(client, "25")
    headers = _auth_headers(login["access_token"])
    user_id = login["user_id"]

    # 只创建 1 个 UserModel，未配 AgentModelMapping
    await _create_model(client, headers, "唯一 GLM-4")

    import asyncpg

    from app.config import get_settings

    settings = get_settings()
    pool = await asyncpg.create_pool(settings.postgres.url, min_size=1, max_size=5)
    try:
        um_service = UserModelService(pool)
        store = AgentModelStore(settings.root_dir)
        service = AgentModelMappingService(store, um_service, settings.projects_dir)

        # 6 个 agent_type 都返回该唯一 UserModel
        for agent_type in ["analyst", "architect", "designer", "planner", "implementer", "critic"]:
            model_id = await service.resolve_model_id(user_id, agent_type)
            assert model_id == "唯一 GLM-4", f"{agent_type} 应智能默认到唯一 UserModel"
    finally:
        await pool.close()


async def test_ar_2_6_multi_user_model_no_mapping_guides(client: AsyncClient) -> None:
    """AR-2.6 多 UserModel 未配置时引导"""
    login = await _register_and_login(client, "26")
    headers = _auth_headers(login["access_token"])
    user_id = login["user_id"]

    # 2 个 UserModel，未配 AgentModelMapping
    await _create_model(client, headers, "GLM-4")
    await _create_model(client, headers, "Claude")

    import asyncpg

    from app.config import get_settings

    settings = get_settings()
    pool = await asyncpg.create_pool(settings.postgres.url, min_size=1, max_size=5)
    try:
        um_service = UserModelService(pool)
        store = AgentModelStore(settings.root_dir)
        service = AgentModelMappingService(store, um_service, settings.projects_dir)

        from app.biz.agent_models.service import ModelNotConfiguredError

        with __import__("pytest").raises(ModelNotConfiguredError) as exc_info:
            await service.resolve_model_id(user_id, "analyst")

        # 异常消息含引导信息
        assert "analyst" in str(exc_info.value)
    finally:
        await pool.close()
