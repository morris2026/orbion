"""OpenAI Agents SDK 事件流 → AgentEvent 序列转换（§6.2.2）。

把 SDK Runner.run_streamed() 产出的事件流转换为 Orbion 内部 AgentEvent 序列：
- RawResponsesStreamEvent.data（ResponseTextDeltaEvent）→ text_delta
- RunItemStreamEvent(name=tool_called) → tool_call（MCP 工具名 mcp__server__tool 保持原样）
- RunItemStreamEvent(name=tool_output) → tool_result
- RunItemStreamEvent(name=mcp_approval_requested) → permission_request（callback_url=POST /runs/{run_id}/permission）
- 流正常结束 → done（usage 来自 get_usage 回调，由调用方从 context_wrapper 提取）
- 流抛异常 → error（redact api_key 模式，复用步骤 2 redact_secrets，与 AR-10.5 联动）

其他 SDK 事件类型（message_output_created / reasoning_item_created / handoff_* /
tool_search_* / mcp_approval_response / mcp_list_tools / agent_updated）当前忽略，
由调用方按需扩展。

tool_result 字段映射遵循 types.py ToolResult 定义（call_id/output/ok/error），
不与设计文档 §6.2.2 表格字段（skill_id/data/duration_ms）一致——types.py 是步骤 3
已确立的事实标准，设计文档表格待后续勘误同步。
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import cast

from agents import (
    MCPApprovalRequestItem,
    RawResponsesStreamEvent,
    RunItemStreamEvent,
    ToolCallItem,
    ToolCallOutputItem,
)
from agents.stream_events import StreamEvent

from app.biz.agents.adapters.types import (
    AgentEvent,
    AgentEventKind,
    PermissionRequest,
    ToolCall,
    ToolResult,
    UsageInfo,
)
from app.biz.user_models.encryption import redact_secrets

logger = logging.getLogger(__name__)


async def translate_openai_stream_events(
    sdk_events: AsyncIterator[StreamEvent],
    run_id: str,
    get_usage: Callable[[], Awaitable[UsageInfo | None]],
) -> AsyncIterator[AgentEvent]:
    """把 SDK 事件流转换为 AgentEvent 序列（§6.2.2）。

    流正常结束 yield done（usage 提取失败时降级为 None，不阻断 done）；
    流抛异常 yield error（已 redact）后终止，不继续 yield done。
    """
    try:
        async for event in sdk_events:
            async for agent_event in _convert_event(event, run_id):
                yield agent_event
    except Exception as exc:
        msg = redact_secrets(str(exc))
        logger.exception("translate_openai_stream_events caught SDK stream error run_id=%s", run_id)
        yield AgentEvent(kind=AgentEventKind.ERROR, error=msg)
        return

    try:
        usage = await get_usage()
    except Exception:
        logger.exception("translate_openai_stream_events get_usage failed run_id=%s", run_id)
        usage = None
    yield AgentEvent(kind=AgentEventKind.DONE, usage=usage)


async def _convert_event(event: StreamEvent, run_id: str) -> AsyncIterator[AgentEvent]:
    """单个 SDK 事件 → 0 或多个 AgentEvent。"""
    if isinstance(event, RawResponsesStreamEvent):
        data = event.data
        if getattr(data, "type", None) == "response.output_text.delta":
            yield AgentEvent(kind=AgentEventKind.TEXT_DELTA, delta=getattr(data, "delta", ""))
        return

    if isinstance(event, RunItemStreamEvent):
        if event.name == "tool_called" and isinstance(event.item, ToolCallItem):
            raw: object = event.item.raw_item
            yield AgentEvent(
                kind=AgentEventKind.TOOL_CALL,
                tool_call=ToolCall(
                    call_id=_get_field(raw, "call_id", ""),
                    name=_get_field(raw, "name", ""),
                    arguments=_parse_arguments(_get_field(raw, "arguments", "{}")),
                ),
            )
        elif event.name == "tool_output" and isinstance(event.item, ToolCallOutputItem):
            raw = event.item.raw_item
            output = _get_field(raw, "output", "")
            output_str = output if isinstance(output, str) else json.dumps(output)
            yield AgentEvent(
                kind=AgentEventKind.TOOL_RESULT,
                tool_result=ToolResult(
                    call_id=_get_field(raw, "call_id", ""),
                    output=output_str,
                    ok=_infer_ok(output_str),
                ),
            )
        elif event.name == "mcp_approval_requested" and isinstance(event.item, MCPApprovalRequestItem):
            raw = event.item.raw_item
            yield AgentEvent(
                kind=AgentEventKind.PERMISSION_REQUEST,
                permission_request=PermissionRequest(
                    run_id=run_id,
                    callback_url=f"POST /runs/{run_id}/permission",
                    skill_id=_get_field(raw, "name", ""),
                    arguments=_parse_arguments(_get_field(raw, "arguments", "{}")),
                ),
            )
        return


def _get_field[T](raw: object, name: str, default: T) -> T:
    """从 raw_item 取字段，同时支持 pydantic 模型（属性访问）与 TypedDict/dict（键访问）。

    调用方需保证 default 类型与 raw_item 字段类型一致；cast 仅用于通过 mypy，
    运行时无类型检查（SDK raw_item 字段类型稳定，可接受）。
    """
    if isinstance(raw, dict):
        value = raw.get(name, default)
    else:
        value = getattr(raw, name, default)
    return cast("T", value)


def _parse_arguments(raw: str) -> dict[str, object]:
    """把 SDK 工具调用的 arguments（JSON 字符串）解析为 dict，失败返回空 dict。"""
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {"_value": parsed}


def _infer_ok(output_str: str) -> bool:
    """从 tool_output 字符串推断 ok 状态。

    JSON 含 ok 字段时按其值判断（bool 直接用；字符串 "false"/"0" 视为 False）；
    否则默认 True。MCP 工具 output 来自第三方，需防御字符串型 ok。
    """
    try:
        payload = json.loads(output_str)
    except json.JSONDecodeError:
        return True
    if isinstance(payload, dict) and "ok" in payload:
        ok_val = payload["ok"]
        if isinstance(ok_val, bool):
            return ok_val
        if isinstance(ok_val, str):
            return ok_val.lower() not in {"false", "0", "no"}
        return bool(ok_val)
    return True
