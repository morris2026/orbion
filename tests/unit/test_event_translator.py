"""event_translator UT：AR-5.6–AR-5.10。

验证 SDK 事件流 → AgentEvent 序列转换：text_delta、tool_call（MCP 命名空间保留）、
tool_result、permission_request（callback_url）、done（usage）、error redact。
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from agents import (
    Agent,
    MCPApprovalRequestItem,
    RawResponsesStreamEvent,
    RunItemStreamEvent,
    ToolCallItem,
    ToolCallOutputItem,
)
from openai.types.responses import (
    ResponseFunctionToolCall,
    ResponseTextDeltaEvent,
)
from openai.types.responses.response_input_item_param import FunctionCallOutput
from openai.types.responses.response_output_item import McpApprovalRequest

from app.biz.agents.adapters.event_translator import (
    translate_openai_stream_events,
)
from app.biz.agents.adapters.types import AgentEventKind, UsageInfo
from app.biz.user_models.encryption import redact_secrets

_TEST_AGENT = Agent(name="test")


def _text_delta_event(delta: str) -> ResponseTextDeltaEvent:
    return ResponseTextDeltaEvent(
        content_index=0,
        delta=delta,
        item_id="msg_1",
        logprobs=[],
        output_index=0,
        sequence_number=1,
        type="response.output_text.delta",
    )


def _function_tool_call(name: str, call_id: str = "call_1") -> ResponseFunctionToolCall:
    return ResponseFunctionToolCall(
        arguments=json.dumps({"path": "/tmp/foo"}),
        call_id=call_id,
        name=name,
        type="function_call",
    )


def _function_tool_output(call_id: str = "call_1", output: str = '{"ok":true}') -> FunctionCallOutput:
    return FunctionCallOutput(
        call_id=call_id,
        output=output,
        type="function_call_output",
    )


async def _collect(events: AsyncIterator[Any]) -> list[Any]:
    return [e async for e in events]


async def _empty_usage() -> UsageInfo | None:
    return UsageInfo(input_tokens=100, output_tokens=50, model_name="gpt-4o")


async def test_text_delta_from_raw_responses_stream_event() -> None:
    # AR-5.6：RawResponsesStreamEvent.delta → text_delta AgentEvent
    sdk_events = _async_iter([RawResponsesStreamEvent(data=_text_delta_event("Hello "))])

    events = await _collect(translate_openai_stream_events(sdk_events, "r-1", _empty_usage))

    text_events = [e for e in events if e.kind is AgentEventKind.TEXT_DELTA]
    assert len(text_events) == 1
    assert text_events[0].delta == "Hello "


async def test_tool_call_preserves_mcp_namespace() -> None:
    # AR-5.7：tool_called + mcp__filesystem__read_file → tool_call.name 保持原样
    item = ToolCallItem(
        agent=_TEST_AGENT, raw_item=_function_tool_call(name="mcp__filesystem__read_file", call_id="call_42")
    )
    sdk_events = _async_iter([RunItemStreamEvent(name="tool_called", item=item)])

    events = await _collect(translate_openai_stream_events(sdk_events, "r-1", _empty_usage))

    tool_calls = [e for e in events if e.kind is AgentEventKind.TOOL_CALL]
    assert len(tool_calls) == 1
    assert tool_calls[0].tool_call.name == "mcp__filesystem__read_file"
    assert tool_calls[0].tool_call.call_id == "call_42"
    assert tool_calls[0].tool_call.arguments == {"path": "/tmp/foo"}


async def test_tool_result_field_mapping() -> None:
    # AR-5.8：tool_output → tool_result.skill_id=call_id, ok=True
    item = ToolCallOutputItem(
        agent=_TEST_AGENT,
        raw_item=_function_tool_output(call_id="call_42", output='{"ok":true}'),
        output='{"ok":true}',
    )
    sdk_events = _async_iter([RunItemStreamEvent(name="tool_output", item=item)])

    events = await _collect(translate_openai_stream_events(sdk_events, "r-1", _empty_usage))

    tool_results = [e for e in events if e.kind is AgentEventKind.TOOL_RESULT]
    assert len(tool_results) == 1
    assert tool_results[0].tool_result.call_id == "call_42"
    assert tool_results[0].tool_result.ok is True


async def test_permission_request_carries_callback_url() -> None:
    # AR-5.9：mcp_approval_requested + run_id="r-42" → permission_request(callback_url=POST /runs/r-42/permission)
    raw = McpApprovalRequest(
        id="appr_1",
        arguments=json.dumps({"path": "/tmp/foo"}),
        name="mcp__filesystem__read_file",
        server_label="filesystem",
        type="mcp_approval_request",
    )
    item = MCPApprovalRequestItem(agent=_TEST_AGENT, raw_item=raw)
    sdk_events = _async_iter([RunItemStreamEvent(name="mcp_approval_requested", item=item)])

    events = await _collect(translate_openai_stream_events(sdk_events, "r-42", _empty_usage))

    perm_events = [e for e in events if e.kind is AgentEventKind.PERMISSION_REQUEST]
    assert len(perm_events) == 1
    assert perm_events[0].permission_request.run_id == "r-42"
    assert perm_events[0].permission_request.callback_url == "POST /runs/r-42/permission"
    assert perm_events[0].permission_request.skill_id == "mcp__filesystem__read_file"


async def test_done_event_usage_from_get_usage_callback() -> None:
    # AR-5.10：流结束 → done AgentEvent.usage 来自 get_usage
    sdk_events = _async_iter([])

    events = await _collect(translate_openai_stream_events(sdk_events, "r-1", _empty_usage))

    done_events = [e for e in events if e.kind is AgentEventKind.DONE]
    assert len(done_events) == 1
    assert done_events[0].usage is not None
    assert done_events[0].usage.input_tokens == 100
    assert done_events[0].usage.output_tokens == 50


async def test_done_event_yields_even_when_get_usage_returns_none() -> None:
    # 边界：get_usage 返回 None 时 done 事件仍 yield，usage 为 None
    async def _none_usage() -> UsageInfo | None:
        return None

    sdk_events = _async_iter([])

    events = await _collect(translate_openai_stream_events(sdk_events, "r-1", _none_usage))

    done_events = [e for e in events if e.kind is AgentEventKind.DONE]
    assert len(done_events) == 1
    assert done_events[0].usage is None


async def test_done_event_yields_when_get_usage_raises() -> None:
    # 边界：get_usage 抛异常时降级为 usage=None，done 事件仍 yield（不转化为 error）
    async def _boom_usage() -> UsageInfo | None:
        raise RuntimeError("usage extract failed")

    sdk_events = _async_iter([])

    events = await _collect(translate_openai_stream_events(sdk_events, "r-1", _boom_usage))

    done_events = [e for e in events if e.kind is AgentEventKind.DONE]
    assert len(done_events) == 1
    assert done_events[0].usage is None
    assert not [e for e in events if e.kind is AgentEventKind.ERROR]


async def test_non_text_delta_raw_events_are_ignored() -> None:
    # 边界：非 response.output_text.delta 的 raw event 被忽略，不产生 AgentEvent（除 done）
    from openai.types.responses import ResponseContentPartDoneEvent, ResponseOutputText

    non_delta_event = ResponseContentPartDoneEvent(
        content_index=0,
        item_id="msg_1",
        output_index=0,
        part=ResponseOutputText(annotations=[], text="ignored", type="output_text", logprobs=None),
        sequence_number=2,
        type="response.content_part.done",
    )
    sdk_events = _async_iter([RawResponsesStreamEvent(data=non_delta_event)])

    events = await _collect(translate_openai_stream_events(sdk_events, "r-1", _empty_usage))

    assert [e for e in events if e.kind is AgentEventKind.TEXT_DELTA] == []
    assert len([e for e in events if e.kind is AgentEventKind.DONE]) == 1


async def test_error_event_redacts_api_key_patterns() -> None:
    # AR-5.10：SDK 流抛异常含长 api_key → error AgentEvent.error 已 redact
    long_key = "sk-abcdefghijklmnopqrstuvwxyz0123456789"

    async def _boom() -> AsyncIterator[Any]:
        if False:
            yield  # 让函数成为 async generator
        raise RuntimeError(f"upstream 5xx Bearer {long_key} in header")

    events = await _collect(translate_openai_stream_events(_boom(), "r-1", _empty_usage))

    error_events = [e for e in events if e.kind is AgentEventKind.ERROR]
    assert len(error_events) == 1
    assert long_key not in error_events[0].error
    assert "***" in error_events[0].error


def test_redact_event_error_replaces_api_key_patterns() -> None:
    # AR-5.10 redact：复用 redact_secrets，验证 sk- / Bearer / api_key= 三类模式（≥20 字符）
    long_key = "sk-abcdefghijklmnopqrstuvwxyz0123456789"
    raw = f"auth=Bearer {long_key} api_key={long_key}"
    redacted = redact_secrets(raw)

    assert long_key not in redacted
    assert redacted.count("***") >= 2


# ---------- helpers ----------


def _async_iter(items: list[Any]) -> AsyncIterator[Any]:
    async def _gen() -> AsyncIterator[Any]:
        for item in items:
            yield item

    return _gen()
