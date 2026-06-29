"""skill_translator UT：AR-5.1–AR-5.5。

验证 SkillDeclaration → FunctionTool 翻译：risk_level 映射 needs_approval、
parameters_schema 透传、adapt_handler dict→Pydantic→SkillResult→JSON str、失败 reason 传播。
"""

from __future__ import annotations

import json
from typing import Any

from agents.tool_context import ToolContext
from pydantic import BaseModel

from app.biz.agents.adapters.skill_translator import translate_skill_to_function_tool
from app.biz.agents.adapters.types import RiskLevel, SkillDeclaration, SkillResult


class FileReadParams(BaseModel):
    path: str


def _skill(risk: RiskLevel, skill_id: str = "file.read") -> SkillDeclaration:
    return SkillDeclaration(
        skill_id=skill_id,
        risk_level=risk,
        description=f"{skill_id} skill",
        parameters_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    )


async def _ok_handler(params: FileReadParams) -> SkillResult:
    assert params.path == "/tmp/foo"
    return SkillResult(ok=True, data={"content": "hello"})


async def _deny_handler(params: FileReadParams) -> SkillResult:
    return SkillResult(ok=False, reason="permission denied")


def _make_ctx() -> ToolContext[Any]:
    # ToolContext 构造较重，用最小 mock
    return ToolContext.__new__(ToolContext)


async def test_low_risk_maps_to_no_approval() -> None:
    # AR-5.1：LOW → needs_approval=False
    tool = translate_skill_to_function_tool(_skill(RiskLevel.LOW), _ok_handler, FileReadParams)

    assert tool.name == "file.read"
    assert tool.description == "file.read skill"
    assert tool.needs_approval is False
    assert "properties" in tool.params_json_schema


async def test_medium_risk_maps_to_no_approval() -> None:
    # AR-5.2：MEDIUM → needs_approval=False（路径校验由 SkillPermissionChecker 负责）
    tool = translate_skill_to_function_tool(_skill(RiskLevel.MEDIUM, "file.write"), _ok_handler, FileReadParams)

    assert tool.needs_approval is False


async def test_high_risk_maps_to_approval() -> None:
    # AR-5.3：HIGH → needs_approval=True
    tool = translate_skill_to_function_tool(_skill(RiskLevel.HIGH, "git.commit"), _ok_handler, FileReadParams)

    assert tool.needs_approval is True


async def test_adapt_handler_dict_to_pydantic_to_skill_result_to_json() -> None:
    # AR-5.4：SDK 调 sdk_handler(ctx, json.dumps({"path": "/tmp/foo"}))
    tool = translate_skill_to_function_tool(_skill(RiskLevel.LOW), _ok_handler, FileReadParams)

    raw_output = await tool.on_invoke_tool(_make_ctx(), json.dumps({"path": "/tmp/foo"}))

    payload = json.loads(raw_output)
    assert payload["ok"] is True
    assert payload["data"] == {"content": "hello"}


async def test_adapt_handler_propagates_failure_reason() -> None:
    # AR-5.5：handler 返回 SkillResult(ok=False, reason=...) → JSON str 含 ok=False + reason
    tool = translate_skill_to_function_tool(_skill(RiskLevel.LOW), _deny_handler, FileReadParams)

    raw_output = await tool.on_invoke_tool(_make_ctx(), json.dumps({"path": "/tmp/foo"}))

    payload = json.loads(raw_output)
    assert payload["ok"] is False
    assert payload["reason"] == "permission denied"


async def test_adapt_handler_invalid_json_returns_failure() -> None:
    # 边界：非法 JSON 参数 → SkillResult(ok=False)
    tool = translate_skill_to_function_tool(_skill(RiskLevel.LOW), _ok_handler, FileReadParams)

    raw_output = await tool.on_invoke_tool(_make_ctx(), "not-json")

    payload = json.loads(raw_output)
    assert payload["ok"] is False
    assert "reason" in payload


async def test_adapt_handler_validation_failure_returns_failure() -> None:
    # 边界：参数校验失败 → SkillResult(ok=False)
    tool = translate_skill_to_function_tool(_skill(RiskLevel.LOW), _ok_handler, FileReadParams)

    raw_output = await tool.on_invoke_tool(_make_ctx(), json.dumps({"wrong_field": "x"}))

    payload = json.loads(raw_output)
    assert payload["ok"] is False
    assert "reason" in payload


async def test_strict_json_schema_disabled_for_schema_passthrough() -> None:
    # AR-5.14：strict_json_schema=False 保证 parameters_schema 直接透传
    skill = _skill(RiskLevel.LOW)
    tool = translate_skill_to_function_tool(skill, _ok_handler, FileReadParams)

    assert tool.strict_json_schema is False
    assert tool.params_json_schema == skill.parameters_schema
