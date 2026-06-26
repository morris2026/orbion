"""UserModel 数据模型与 API schemas"""

from typing import Any, Literal

from pydantic import BaseModel, Field

Provider = Literal["openai", "anthropic", "azure_openai", "openai_compat"]


class UserModelCreate(BaseModel):
    model_id: str = Field(..., min_length=1, max_length=64)
    provider: Provider
    model_name: str = Field(..., min_length=1, max_length=128)
    base_url: str = Field(..., min_length=1, max_length=256)
    api_key: str = Field(..., min_length=1)
    extra_config: dict[str, Any] = Field(default_factory=dict)


class UserModelUpdate(BaseModel):
    """UserModel 更新请求

    所有字段 None 表示"不更新"（保持原值）；提供值则覆盖。
    extra_config 的 None 与 {} 语义不同：
    - None：不更新 extra_config（保持原值）
    - {}：清空 extra_config 为空 dict
    """

    provider: Provider | None = None
    model_name: str | None = None
    base_url: str | None = None
    api_key: str | None = None  # None 表示不变更
    extra_config: dict[str, Any] | None = None


class UserModelResponse(BaseModel):
    id: str
    user_id: str
    model_id: str
    provider: Provider
    model_name: str
    base_url: str
    api_key_masked: str  # "sk-***ef" 脱敏展示
    extra_config: dict[str, Any]


def mask_api_key(api_key: str) -> str:
    """脱敏：保留前 3 + *** + 后 2，过短则全 ***"""
    if len(api_key) <= 5:
        return "***"
    return f"{api_key[:3]}***{api_key[-2:]}"
