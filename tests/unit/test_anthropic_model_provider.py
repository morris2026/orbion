"""AnthropicModelProvider UT：AR-6.1–AR-6.5。

验证 Anthropic usage 字段映射、messages role=user content 数组、tool_use↔function_call 双向转换、
tool_result 嵌入 user 消息、流式 content_block_delta 转 text_delta。
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any, cast
from unittest.mock import MagicMock

from agents.items import TResponseInputItem
from anthropic.types import (
    Message,
    RawContentBlockDeltaEvent,
    TextBlock,
    TextDelta,
    Usage,
)

from app.biz.agents.adapters.anthropic_provider import (
    AnthropicModel,
    AnthropicModelProvider,
    anthropic_usage_to_usage_info,
    convert_input,
    convert_response,
    convert_tools,
)


def _usage(
    input_tokens: int = 100,
    output_tokens: int = 50,
    cache_read: int | None = 30,
) -> Usage:
    return Usage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_input_tokens=cache_read,
    )


def test_anthropic_usage_maps_to_usage_info() -> None:
    # AR-6.1：cache_read_input_tokens → cache_hit_tokens，estimated=False
    usage = _usage(input_tokens=100, output_tokens=50, cache_read=30)

    info = anthropic_usage_to_usage_info(usage, model_name="claude-sonnet-4-6")

    assert info.input_tokens == 100
    assert info.output_tokens == 50
    assert info.cache_hit_tokens == 30
    assert info.estimated is False
    assert info.model_name == "claude-sonnet-4-6"


def test_anthropic_usage_with_none_cache_read_defaults_to_zero() -> None:
    # 边界：cache_read_input_tokens=None → cache_hit_tokens=0
    usage = _usage(cache_read=None)

    info = anthropic_usage_to_usage_info(usage, model_name="claude-sonnet-4-6")

    assert info.cache_hit_tokens == 0


def test_convert_input_user_message_content_is_array() -> None:
    # AR-6.2：role=user 时 Anthropic content 是数组 [{"type":"text","text":...}]
    input_items = cast(
        "list[TResponseInputItem]",
        [
            {"role": "user", "content": "你好"},
        ],
    )

    messages, system = convert_input(input_items, system_instructions="你是助手")

    assert system == "你是助手"
    assert len(messages) == 1
    msg = messages[0]
    assert msg["role"] == "user"
    assert isinstance(msg["content"], list)
    assert msg["content"] == [{"type": "text", "text": "你好"}]


def test_convert_input_function_call_becomes_assistant_tool_use() -> None:
    # AR-6.3：OpenAI function_call → Anthropic assistant tool_use（arguments JSON str ↔ input dict）
    input_items = cast(
        "list[TResponseInputItem]",
        [
            {
                "type": "function_call",
                "call_id": "call_1",
                "name": "file.read",
                "arguments": json.dumps({"path": "/tmp/foo"}),
            },
        ],
    )

    messages, _ = convert_input(input_items, system_instructions=None)

    assert len(messages) == 1
    msg = messages[0]
    assert msg["role"] == "assistant"
    blocks = msg["content"]
    tool_use = next(b for b in blocks if b["type"] == "tool_use")
    assert tool_use["id"] == "call_1"
    assert tool_use["name"] == "file.read"
    assert tool_use["input"] == {"path": "/tmp/foo"}


def test_convert_input_function_call_output_embeds_in_user_message() -> None:
    # AR-6.4：OpenAI function_call_output → Anthropic tool_result 嵌入 user 消息
    input_items = cast(
        "list[TResponseInputItem]",
        [
            {
                "type": "function_call_output",
                "call_id": "call_1",
                "output": '{"ok": true}',
            },
        ],
    )

    messages, _ = convert_input(input_items, system_instructions=None)

    assert len(messages) == 1
    msg = messages[0]
    assert msg["role"] == "user"
    tool_result = next(b for b in msg["content"] if b["type"] == "tool_result")
    assert tool_result["tool_use_id"] == "call_1"
    assert tool_result["content"] == '{"ok": true}'


def test_convert_input_merges_adjacent_same_role_messages() -> None:
    # 边界：相邻同角色 message 合并 content（Anthropic API 要求 roles must alternate）
    input_items = cast(
        "list[TResponseInputItem]",
        [
            {"role": "user", "content": "你好"},
            {"role": "user", "content": "再见"},
        ],
    )

    messages, _ = convert_input(input_items, system_instructions=None)

    assert len(messages) == 1
    msg = messages[0]
    assert msg["role"] == "user"
    assert msg["content"] == [
        {"type": "text", "text": "你好"},
        {"type": "text", "text": "再见"},
    ]


def test_convert_input_function_call_output_dict_wraps_as_content_block() -> None:
    # 边界：output 为 dict 时包装为 [{"type":"text","text": json}] 保留结构
    input_items = cast(
        "list[TResponseInputItem]",
        [
            {
                "type": "function_call_output",
                "call_id": "call_1",
                "output": {"ok": True, "data": [1, 2, 3]},
            },
        ],
    )

    messages, _ = convert_input(input_items, system_instructions=None)

    tool_result = next(b for b in messages[0]["content"] if b["type"] == "tool_result")
    assert isinstance(tool_result["content"], list)
    assert tool_result["content"][0]["type"] == "text"
    assert json.loads(tool_result["content"][0]["text"]) == {"ok": True, "data": [1, 2, 3]}


def test_convert_tools_function_tool_to_anthropic_tool() -> None:
    # AR-6.3：FunctionTool → Anthropic tool（input_schema）
    from agents import FunctionTool

    async def _handler(_ctx: object, _raw: str) -> str:
        return '{"ok":true}'

    tool = FunctionTool(
        name="file.read",
        description="read a file",
        params_json_schema={"type": "object", "properties": {"path": {"type": "string"}}},
        on_invoke_tool=_handler,
        strict_json_schema=False,
    )

    anthropic_tools = convert_tools([tool])

    assert len(anthropic_tools) == 1
    at = anthropic_tools[0]
    assert at["name"] == "file.read"
    assert at["description"] == "read a file"
    assert at["input_schema"] == {"type": "object", "properties": {"path": {"type": "string"}}}


def test_convert_response_text_block_to_output_message() -> None:
    # AR-6.3 反向：Anthropic TextBlock → ResponseOutputMessage
    msg = Message(
        id="msg_1",
        content=[TextBlock(text="hello world", type="text")],
        model="claude-sonnet-4-6",
        role="assistant",
        stop_reason="end_turn",
        type="message",
        usage=_usage(),
    )

    resp = convert_response(msg, model_name="claude-sonnet-4-6")

    assert resp.response_id == "msg_1"
    assert resp.usage.input_tokens == 100
    assert resp.usage.output_tokens == 50
    assert resp.usage.input_tokens_details.cached_tokens == 30
    from openai.types.responses import ResponseOutputMessage as _OutputMessage

    msg_item = next(item for item in resp.output if isinstance(item, _OutputMessage))
    assert any(getattr(c, "text", None) == "hello world" for c in msg_item.content)


def test_convert_response_tool_use_block_to_function_call() -> None:
    # AR-6.3 反向：Anthropic ToolUseBlock → ResponseFunctionToolCall（arguments JSON str）
    from anthropic.types import ToolUseBlock
    from openai.types.responses import ResponseFunctionToolCall as _FunctionCall

    msg = Message(
        id="msg_1",
        content=[
            ToolUseBlock(id="call_1", input={"path": "/tmp/foo"}, name="file.read", type="tool_use"),
        ],
        model="claude-sonnet-4-6",
        role="assistant",
        stop_reason="tool_use",
        type="message",
        usage=_usage(),
    )

    resp = convert_response(msg, model_name="claude-sonnet-4-6")

    fc = next(item for item in resp.output if isinstance(item, _FunctionCall))
    assert fc.call_id == "call_1"
    assert fc.name == "file.read"
    assert json.loads(fc.arguments) == {"path": "/tmp/foo"}


async def test_stream_response_yields_text_delta_event() -> None:
    # AR-6.5：流式 content_block_delta（type=text_delta）→ response.output_text.delta
    delta_event = RawContentBlockDeltaEvent(
        delta=TextDelta(text="Hello ", type="text_delta"),
        index=0,
        type="content_block_delta",
    )
    final_msg = Message(
        id="msg_1",
        content=[TextBlock(text="Hello ", type="text")],
        model="claude-sonnet-4-6",
        role="assistant",
        stop_reason="end_turn",
        type="message",
        usage=_usage(),
    )

    class _FakeStream:
        def __init__(self) -> None:
            self._events = [delta_event]

        async def __aenter__(self) -> _FakeStream:
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        def __aiter__(self) -> AsyncIterator[Any]:
            async def _gen() -> AsyncIterator[Any]:
                for ev in self._events:
                    yield ev

            return _gen()

        async def get_final_message(self) -> Message:
            return final_msg

    mock_messages = MagicMock()
    mock_messages.stream.return_value = _FakeStream()
    mock_client = MagicMock()
    mock_client.messages = mock_messages

    model = AnthropicModel(mock_client, "claude-sonnet-4-6")

    events = []
    async for ev in model.stream_response(
        system_instructions="你是助手",
        input=[{"role": "user", "content": "hi"}],
        model_settings=__import__("agents").ModelSettings(),
        tools=[],
        output_schema=None,
        handoffs=[],
        tracing=__import__("agents").ModelTracing.DISABLED,
        previous_response_id=None,
        conversation_id=None,
        prompt=None,
    ):
        events.append(ev)

    from openai.types.responses import ResponseCompletedEvent as _Completed
    from openai.types.responses import ResponseTextDeltaEvent as _TextDelta

    text_deltas = [e for e in events if isinstance(e, _TextDelta)]
    assert len(text_deltas) >= 1
    assert text_deltas[0].delta == "Hello "
    completed = [e for e in events if isinstance(e, _Completed)]
    assert len(completed) == 1


def test_get_model_returns_anthropic_model_with_name() -> None:
    # 边界：get_model(None) 用默认模型名
    mock_client = MagicMock()
    provider = AnthropicModelProvider(mock_client)

    model = provider.get_model(None)

    assert isinstance(model, AnthropicModel)
    assert model.model_name == "claude-sonnet-4-6"
