"""AnthropicModelProvider — openai-agents SDK ModelProvider/Model 实现（§6.3.1）。

把 OpenAI Agents SDK 的 ModelProvider/Model 接口适配到 Anthropic SDK：
- input（OpenAI Responses 格式）→ Anthropic messages（content 是数组）
- tools（FunctionTool）→ Anthropic tools（input_schema）
- tool 结果（function_call_output）→ Anthropic tool_result（嵌入 user 消息）
- response：Anthropic message → ModelResponse（TextBlock→ResponseOutputMessage,
  ToolUseBlock→ResponseFunctionToolCall，arguments JSON 字符串 ↔ input dict）
- usage：Anthropic Usage → SDK Usage（cache_read_input_tokens → input_tokens_details.cached_tokens）
- 流式：content_block_delta（type=text_delta）→ response.output_text.delta

限制（MVP 裁剪）：
- 不支持 handoffs / output_schema 强制 tool_use（参数接收但忽略）
- tracing 参数接收但 MVP 不发射 trace span（模型调用段在 trace 中空缺，
  步骤 24 可观测性收尾时补）
- 流式仅透传 text_delta；tool_use 增量（input_json_delta）静默丢弃，
  tool_call 仅在 response.completed 事件中给出（SDK Runner 在此模式下
  能否触发 tool 循环由步骤 7 集成测试 / E2E 验证）
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any, cast

from agents import (
    AgentOutputSchemaBase,
    Handoff,
    Model,
    ModelProvider,
    ModelResponse,
    ModelSettings,
    ModelTracing,
    Tool,
)
from agents import (
    Usage as SdkUsage,
)
from agents.items import TResponseInputItem, TResponseStreamEvent
from anthropic import AsyncAnthropic
from anthropic.types import (
    Message as AnthropicMessage,
)
from anthropic.types import (
    RawContentBlockDeltaEvent,
    TextBlock,
    TextDelta,
    ToolUseBlock,
)
from anthropic.types import (
    Usage as AnthropicUsage,
)
from openai.types.responses import (
    Response,
    ResponseCompletedEvent,
    ResponseCreatedEvent,
    ResponseFunctionToolCall,
    ResponseOutputMessage,
    ResponseOutputText,
    ResponsePromptParam,
    ResponseTextDeltaEvent,
    ResponseUsage,
)
from openai.types.responses.response_usage import InputTokensDetails, OutputTokensDetails

from app.biz.agents.adapters.types import UsageInfo

_DEFAULT_MODEL = "claude-sonnet-4-6"


class AnthropicModelProvider(ModelProvider):
    """openai-agents ModelProvider 实现，返回 AnthropicModel。"""

    def __init__(self, client: AsyncAnthropic) -> None:
        self._client = client

    def get_model(self, model_name: str | None) -> AnthropicModel:
        return AnthropicModel(self._client, model_name or _DEFAULT_MODEL)


class AnthropicModel(Model):
    """openai-agents Model 实现，封装 Anthropic messages API。"""

    def __init__(self, client: AsyncAnthropic, model_name: str) -> None:
        self._client = client
        self._model_name = model_name

    @property
    def model_name(self) -> str:
        return self._model_name

    async def get_response(
        self,
        system_instructions: str | None,
        input: str | list[TResponseInputItem],
        model_settings: ModelSettings,
        tools: list[Tool],
        output_schema: AgentOutputSchemaBase | None,
        handoffs: list[Handoff],
        tracing: ModelTracing,
        *,
        previous_response_id: str | None,
        conversation_id: str | None,
        prompt: ResponsePromptParam | None,
    ) -> ModelResponse:
        messages, system = convert_input(input, system_instructions)
        anthropic_tools = convert_tools(tools)
        kwargs: dict[str, Any] = {
            "model": self._model_name,
            "messages": messages,
            "max_tokens": model_settings.max_tokens or 4096,
        }
        if system is not None:
            kwargs["system"] = system
        if anthropic_tools:
            kwargs["tools"] = anthropic_tools
        if model_settings.temperature is not None:
            kwargs["temperature"] = model_settings.temperature
        if model_settings.top_p is not None:
            kwargs["top_p"] = model_settings.top_p
        resp = await self._client.messages.create(**kwargs)
        return convert_response(resp, self._model_name)

    async def stream_response(
        self,
        system_instructions: str | None,
        input: str | list[TResponseInputItem],
        model_settings: ModelSettings,
        tools: list[Tool],
        output_schema: AgentOutputSchemaBase | None,
        handoffs: list[Handoff],
        tracing: ModelTracing,
        *,
        previous_response_id: str | None,
        conversation_id: str | None,
        prompt: ResponsePromptParam | None,
    ) -> AsyncIterator[TResponseStreamEvent]:
        messages, system = convert_input(input, system_instructions)
        anthropic_tools = convert_tools(tools)
        kwargs: dict[str, Any] = {
            "model": self._model_name,
            "messages": messages,
            "max_tokens": model_settings.max_tokens or 4096,
        }
        if system is not None:
            kwargs["system"] = system
        if anthropic_tools:
            kwargs["tools"] = anthropic_tools
        if model_settings.temperature is not None:
            kwargs["temperature"] = model_settings.temperature
        if model_settings.top_p is not None:
            kwargs["top_p"] = model_settings.top_p

        msg_id = f"msg_{uuid.uuid4().hex[:24]}"
        sequence = 0
        output_index = 0
        content_index = 0

        async with self._client.messages.stream(**kwargs) as stream:
            # 先发 response.created
            yield ResponseCreatedEvent(
                response=Response(
                    id=msg_id,
                    created_at=0,
                    model=self._model_name,
                    object="response",
                    status="in_progress",
                    output=[],
                    tools=[],
                    parallel_tool_calls=False,
                    tool_choice="auto",
                    top_p=kwargs.get("top_p"),
                    reasoning=None,
                    text=None,
                    truncation="disabled",
                    usage=None,
                    user=None,
                    metadata={},
                    instructions=system_instructions,
                    temperature=kwargs.get("temperature"),
                    previous_response_id=previous_response_id,
                ),
                sequence_number=sequence,
                type="response.created",
            )
            sequence += 1

            async for event in stream:
                if isinstance(event, RawContentBlockDeltaEvent) and isinstance(event.delta, TextDelta):
                    yield ResponseTextDeltaEvent(
                        content_index=content_index,
                        delta=event.delta.text,
                        item_id=msg_id,
                        logprobs=[],
                        output_index=output_index,
                        sequence_number=sequence,
                        type="response.output_text.delta",
                    )
                    sequence += 1

            final_msg = await stream.get_final_message()
            model_response = convert_response(final_msg, self._model_name)
            yield ResponseCompletedEvent(
                response=_build_response_from_model_response(
                    model_response, msg_id, self._model_name, system_instructions, previous_response_id
                ),
                sequence_number=sequence,
                type="response.completed",
            )


def anthropic_usage_to_usage_info(usage: AnthropicUsage, model_name: str) -> UsageInfo:
    """Anthropic Usage → Orbion UsageInfo（§6.7.2）。

    cache_read_input_tokens → cache_hit_tokens；供方正常返回 estimated=False。
    """
    return UsageInfo(
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cache_hit_tokens=usage.cache_read_input_tokens or 0,
        estimated=False,
        model_name=model_name,
    )


def convert_input(
    input: str | list[TResponseInputItem],
    system_instructions: str | None,
) -> tuple[list[dict[str, Any]], str | None]:
    """OpenAI Responses input → Anthropic messages + system。

    - str → 单条 user message（content 数组）
    - EasyInputMessageParam / ResponseOutputMessageParam（role+content）→ 同角色 message
    - function_call → assistant message 含 tool_use block
    - function_call_output → user message 含 tool_result block

    相邻同角色 message 自动合并 content 数组（Anthropic API 要求 roles must alternate）。
    """
    if isinstance(input, str):
        return [{"role": "user", "content": [{"type": "text", "text": input}]}], system_instructions

    messages: list[dict[str, Any]] = []
    for raw_item in input:
        if not isinstance(raw_item, dict):
            continue
        item: dict[str, Any] = cast("dict[str, Any]", raw_item)
        item_type = item.get("type")
        if item_type == "function_call":
            new_msg = _convert_function_call_input(item)
        elif item_type == "function_call_output":
            new_msg = _convert_function_call_output_input(item)
        else:
            new_msg = _convert_message_input(item)
        _merge_if_same_role(messages, new_msg)
    return messages, system_instructions


def _merge_if_same_role(messages: list[dict[str, Any]], new_msg: dict[str, Any]) -> None:
    """若 new_msg 与 messages 末尾同 role，合并 content 数组；否则追加。"""
    if messages and messages[-1]["role"] == new_msg["role"]:
        messages[-1]["content"].extend(new_msg["content"])
    else:
        messages.append(new_msg)


def convert_tools(tools: list[Tool]) -> list[dict[str, Any]]:
    """FunctionTool → Anthropic tool（name / description / input_schema）。"""
    anthropic_tools: list[dict[str, Any]] = []
    for tool in tools:
        params_json_schema = getattr(tool, "params_json_schema", None)
        if params_json_schema is None:
            continue
        anthropic_tools.append(
            {
                "name": tool.name,
                "description": getattr(tool, "description", "") or "",
                "input_schema": params_json_schema,
            }
        )
    return anthropic_tools


def convert_response(resp: AnthropicMessage, model_name: str) -> ModelResponse:
    """Anthropic Message → SDK ModelResponse。

    TextBlock → ResponseOutputMessage；ToolUseBlock → ResponseFunctionToolCall。
    """
    output: list[Any] = []
    text_parts: list[str] = []
    for block in resp.content:
        if isinstance(block, TextBlock):
            text_parts.append(block.text)
        elif isinstance(block, ToolUseBlock):
            output.append(
                ResponseFunctionToolCall(
                    arguments=json.dumps(block.input),
                    call_id=block.id,
                    name=block.name,
                    type="function_call",
                )
            )

    if text_parts:
        output.insert(
            0,
            ResponseOutputMessage(
                id=f"msg_{uuid.uuid4().hex[:24]}",
                content=[ResponseOutputText(text="".join(text_parts), type="output_text", annotations=[])],
                role="assistant",
                status="completed",
                type="message",
            ),
        )

    return ModelResponse(
        output=output,
        usage=_anthropic_usage_to_sdk_usage(resp.usage),
        response_id=resp.id,
        request_id=None,
    )


def _anthropic_usage_to_sdk_usage(usage: AnthropicUsage) -> SdkUsage:
    """Anthropic Usage → SDK Usage（cache_read_input_tokens → cached_tokens）。"""
    return SdkUsage(
        requests=1,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        input_tokens_details=InputTokensDetails(cached_tokens=usage.cache_read_input_tokens or 0),
        output_tokens_details=OutputTokensDetails(reasoning_tokens=0),
        total_tokens=usage.input_tokens + usage.output_tokens,
    )


def _convert_message_input(item: dict[str, Any]) -> dict[str, Any]:
    """EasyInputMessageParam / ResponseOutputMessageParam → Anthropic message。"""
    role = item.get("role", "user")
    content = item.get("content", "")
    if isinstance(content, str):
        return {"role": role, "content": [{"type": "text", "text": content}]}
    # content 已经是 list[dict]（OpenAI 格式）→ 透传
    return {"role": role, "content": content}


def _convert_function_call_input(item: dict[str, Any]) -> dict[str, Any]:
    """OpenAI function_call → Anthropic assistant message 含 tool_use block。"""
    raw_args = item.get("arguments", "{}")
    try:
        parsed_args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
    except json.JSONDecodeError:
        parsed_args = {}
    if not isinstance(parsed_args, dict):
        parsed_args = {"_value": parsed_args}
    return {
        "role": "assistant",
        "content": [
            {
                "type": "tool_use",
                "id": item.get("call_id", item.get("id", "")),
                "name": item.get("name", ""),
                "input": parsed_args,
            }
        ],
    }


def _convert_function_call_output_input(item: dict[str, Any]) -> dict[str, Any]:
    """OpenAI function_call_output → Anthropic user message 含 tool_result block。

    output 为 str 时直接传；为 dict/list 时包装为 [{"type":"text","text": json}] 保留结构。
    """
    output = item.get("output", "")
    if isinstance(output, str):
        tool_content: Any = output
    else:
        tool_content = [{"type": "text", "text": json.dumps(output)}]
    return {
        "role": "user",
        "content": [
            {
                "type": "tool_result",
                "tool_use_id": item.get("call_id", ""),
                "content": tool_content,
            }
        ],
    }


def _build_response_from_model_response(
    model_response: ModelResponse,
    msg_id: str,
    model_name: str,
    system_instructions: str | None,
    previous_response_id: str | None,
) -> Response:
    """把 ModelResponse 包装为 Response 对象（供 ResponseCompletedEvent 使用）。"""
    sdk_usage = model_response.usage
    response_usage = ResponseUsage(
        input_tokens=sdk_usage.input_tokens,
        input_tokens_details=InputTokensDetails(cached_tokens=sdk_usage.input_tokens_details.cached_tokens),
        output_tokens=sdk_usage.output_tokens,
        output_tokens_details=OutputTokensDetails(reasoning_tokens=sdk_usage.output_tokens_details.reasoning_tokens),
        total_tokens=sdk_usage.total_tokens,
    )
    return Response(
        id=msg_id,
        created_at=0,
        model=model_name,
        object="response",
        status="completed",
        output=list(model_response.output),
        tools=[],
        parallel_tool_calls=False,
        tool_choice="auto",
        top_p=None,
        reasoning=None,
        text=None,
        truncation="disabled",
        usage=response_usage,
        user=None,
        metadata={},
        instructions=system_instructions,
        temperature=None,
        previous_response_id=previous_response_id,
    )
