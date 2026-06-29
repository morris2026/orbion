"""OrbionAdapterFactory UT：AR-7.2。

验证 openai_compat 走 OpenAIModelProvider + 自定义 base_url、anthropic 走 AnthropicModelProvider。
"""

from __future__ import annotations

from typing import cast
from unittest.mock import patch
from uuid import uuid4

from openai import AsyncOpenAI

from app.biz.agents.adapters.anthropic_provider import AnthropicModelProvider
from app.biz.agents.adapters.factory import AdapterFactory
from app.biz.agents.adapters.openai import (
    OpenAIAgentRuntimeAdapter,
    OrbionAdapterFactory,
    build_model_provider,
)


class _FakeUserModel:
    """UserModelProtocol 鸭子类型实现。"""

    def __init__(
        self,
        provider: str = "openai_compat",
        model_name: str = "glm-4",
        base_url: str | None = "https://open.bigmodel.cn/api/paas/v4",
        api_key_hash: str = "h1",
    ) -> None:
        self.user_id = uuid4()
        self.model_id = "m1"
        self.model_name = model_name
        self.provider = provider
        self.base_url = base_url
        self.api_key_enc = b"\x00" * 12 + b"\x00" * 16  # 占位加密字节
        self.api_key_hash = api_key_hash


def test_build_model_provider_openai_compat_uses_openai_provider() -> None:
    # AR-7.2：openai_compat → OpenAIProvider（非 AnthropicModelProvider），base_url 透传
    provider, anthropic_client = build_model_provider(
        provider="openai_compat",
        api_key="sk-test",
        base_url="https://open.bigmodel.cn/api/paas/v4",
    )

    assert anthropic_client is None
    assert not isinstance(provider, AnthropicModelProvider)
    inner_client = cast(AsyncOpenAI, _extract_openai_client(provider))
    assert str(inner_client.base_url).rstrip("/") == "https://open.bigmodel.cn/api/paas/v4"


def test_build_model_provider_anthropic_uses_anthropic_provider() -> None:
    # 边界：anthropic → AnthropicModelProvider + 返回 Anthropic client 供 close
    provider, anthropic_client = build_model_provider(
        provider="anthropic",
        api_key="sk-ant-test",
        base_url=None,
    )

    assert isinstance(provider, AnthropicModelProvider)
    assert anthropic_client is not None


def test_build_model_provider_openai_uses_openai_provider() -> None:
    # 边界：openai → OpenAIProvider，无额外 client
    provider, anthropic_client = build_model_provider(
        provider="openai",
        api_key="sk-test",
        base_url=None,
    )

    assert not isinstance(provider, AnthropicModelProvider)
    assert anthropic_client is None


def _extract_openai_client(provider: object) -> object:
    """从 OpenAIProvider 提取内部 AsyncOpenAI client。"""
    get_client = getattr(provider, "_get_client", None)
    if callable(get_client):
        return get_client()
    return getattr(provider, "_client", None)


async def test_factory_get_or_create_returns_openai_adapter() -> None:
    # AR-7.2：AdapterFactory.get_or_create 返回 OpenAIAgentRuntimeAdapter
    factory = OrbionAdapterFactory()

    with patch("app.biz.agents.adapters.openai.decrypt_api_key", return_value=b"sk-test"):
        um = _FakeUserModel(provider="openai_compat")
        adapter = await factory.get_or_create(um)

    assert isinstance(adapter, OpenAIAgentRuntimeAdapter)
    assert adapter.model_name == "glm-4"

    # 第二次命中缓存（不重建）
    with patch("app.biz.agents.adapters.openai.decrypt_api_key", return_value=b"sk-test"):
        adapter2 = await factory.get_or_create(um)
    assert adapter is adapter2

    await factory.close_all()


async def test_factory_is_subclass_of_adapter_factory() -> None:
    # 边界：OrbionAdapterFactory 是 AdapterFactory 子类
    factory = OrbionAdapterFactory()
    assert isinstance(factory, AdapterFactory)
