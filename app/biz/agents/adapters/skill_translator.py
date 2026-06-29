"""SkillDeclaration → OpenAI Agents SDK FunctionTool 翻译（§6.2.1）。

把 Orbion 业务侧的 SkillDeclaration 翻译为 SDK FunctionTool：
- name / description / params_json_schema 直接透传
- risk_level 映射 needs_approval：LOW/MEDIUM=False（路径校验由 SkillPermissionChecker 在
  tool_input_guardrail 检查）、HIGH=True（SDK 触发 interruption 走 permission callback）
- adapt_handler 包装签名：SDK 期望 (ctx, json_str) -> json_str，Orbion handler 是
  (typed_params) -> SkillResult；包装层做 dict/JSON → Pydantic → handler → SkillResult → JSON str

失败传播：参数解析 / 校验失败时返回 SkillResult(ok=False, reason=...)，不抛异常，
让 LLM 收到错误消息可重试（与 §6.6.3 失败处理委托 SDK 一致）。
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from agents import FunctionTool
from agents.tool_context import ToolContext
from pydantic import BaseModel, ValidationError

from app.biz.agents.adapters.types import RiskLevel, SkillDeclaration, SkillResult

SkillHandler = Callable[[Any], Awaitable[SkillResult]]


def translate_skill_to_function_tool(
    skill: SkillDeclaration,
    handler: SkillHandler,
    params_type: type[BaseModel],
) -> FunctionTool:
    """把 SkillDeclaration 翻译为 SDK FunctionTool（§6.2.1）。

    params_json_schema 直接透传业务侧 schema，strict_json_schema=False 关闭 SDK 强制
    strict 模式（避免 SDK 注入 additionalProperties: False / 强制所有字段进 required），
    让业务侧 SkillDeclaration.parameters_schema 保持源语义。
    """
    return FunctionTool(
        name=skill.skill_id,
        description=skill.description,
        params_json_schema=skill.parameters_schema,
        on_invoke_tool=_adapt_handler(handler, params_type),
        needs_approval=skill.risk_level is RiskLevel.HIGH,
        strict_json_schema=False,
    )


def _adapt_handler(
    handler: SkillHandler,
    params_type: type[BaseModel],
) -> Callable[[ToolContext[Any], str], Awaitable[str]]:
    """包装 Orbion handler 为 SDK 期望的 (ctx, json_str) -> json_str 签名。

    参数解析 / 校验失败返回 SkillResult(ok=False)，不抛异常；handler 自身异常透传给 SDK
    由 failure_error_function 处理（§6.6.3 失败处理委托 SDK）。
    """

    async def sdk_handler(_ctx: ToolContext[Any], raw_input: str) -> str:
        try:
            data = json.loads(raw_input) if raw_input else {}
        except json.JSONDecodeError:
            return SkillResult(ok=False, reason=f"invalid JSON arguments: {raw_input!r}").model_dump_json()
        try:
            typed_params = params_type.model_validate(data)
        except ValidationError as exc:
            return SkillResult(ok=False, reason=f"params validation failed: {exc}").model_dump_json()
        result = await handler(typed_params)
        return result.model_dump_json()

    return sdk_handler
