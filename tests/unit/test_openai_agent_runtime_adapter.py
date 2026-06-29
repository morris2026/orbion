"""OpenAIAgentRuntimeAdapter UT：AR-7.1–AR-7.3。

验证 OpenAI usage 字段映射、openai_compat 走 OpenAIModelProvider + 自定义 base_url、
run_streamed 集成 skill_translator + event_translator + Runner。
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from agents import ModelProvider
from openai import AsyncOpenAI
from openai.types.chat.chat_completion_chunk import Choice, ChoiceDelta
from openai.types.completion_usage import CompletionUsage, PromptTokensDetails

from app.biz.agents.adapters.openai import (
    OpenAIAgentRuntimeAdapter,
    openai_usage_to_usage_info,
)
from app.biz.agents.adapters.types import (
    AgentDeclaration,
    PromptInput,
    RiskLevel,
    SkillDeclaration,
)


def _usage(
    prompt_tokens: int = 100,
    completion_tokens: int = 50,
    cached_tokens: int | None = 30,
) -> CompletionUsage:
    return CompletionUsage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
        prompt_tokens_details=PromptTokensDetails(cached_tokens=cached_tokens),
    )


def test_openai_usage_maps_to_usage_info() -> None:
    # AR-7.1：prompt_tokens/completion_tokens/cached_tokens → input/output/cache_hit
    usage = _usage(prompt_tokens=100, completion_tokens=50, cached_tokens=30)

    info = openai_usage_to_usage_info(usage, model_name="gpt-4o")

    assert info.input_tokens == 100
    assert info.output_tokens == 50
    assert info.cache_hit_tokens == 30
    assert info.estimated is False
    assert info.model_name == "gpt-4o"


def test_openai_usage_with_none_cached_defaults_to_zero() -> None:
    # 边界：cached_tokens=None → cache_hit_tokens=0
    usage = _usage(cached_tokens=None)

    info = openai_usage_to_usage_info(usage, model_name="gpt-4o")

    assert info.cache_hit_tokens == 0


def _make_chunk(delta: str | None = None, usage: CompletionUsage | None = None) -> MagicMock:
    choice = Choice(
        delta=ChoiceDelta(content=delta),
        finish_reason=None,
        index=0,
        logprobs=None,
    )
    return MagicMock(choices=[choice] if delta is not None else [], usage=usage)


class _FakeUserModel:
    """UserModelProtocol 鸭子类型实现。"""

    def __init__(
        self,
        model_id: str = "m1",
        model_name: str = "gpt-4o",
        provider: str = "openai",
        base_url: str | None = None,
        api_key_hash: str = "h1",
    ) -> None:
        self.user_id = uuid4()
        self.model_id = model_id
        self.model_name = model_name
        self.provider = provider
        self.base_url = base_url
        self.api_key_hash = api_key_hash


def _build_adapter(
    user_model: _FakeUserModel | None = None,
    provider_client: AsyncOpenAI | None = None,
    model_provider: ModelProvider | None = None,
) -> OpenAIAgentRuntimeAdapter:
    um = user_model or _FakeUserModel()
    client = provider_client or MagicMock(spec=AsyncOpenAI)
    mp = model_provider or MagicMock()
    return OpenAIAgentRuntimeAdapter(um, client, mp)  # type: ignore[arg-type]


async def test_stream_yields_text_deltas_and_done_usage() -> None:
    # AR-7.1：stream() yield text chunks + done chunk 携带 usage
    usage = _usage()
    chunks = [
        _make_chunk(delta="Hello "),
        _make_chunk(delta="World"),
        _make_chunk(usage=usage),
    ]

    async def _fake_stream() -> AsyncIterator[Any]:
        for c in chunks:
            yield c

    mock_client = MagicMock(spec=AsyncOpenAI)
    mock_client.chat = MagicMock()
    mock_client.chat.completions = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=_fake_stream())

    adapter = _build_adapter(provider_client=mock_client)

    events = []
    async for chunk in adapter.stream(PromptInput(system_prompt="sys", task="hi")):
        events.append(chunk)

    text_events = [e for e in events if e.type.value == "text"]
    done_events = [e for e in events if e.type.value == "done"]
    assert len(text_events) == 2
    assert text_events[0].delta == "Hello "
    assert text_events[1].delta == "World"
    assert len(done_events) == 1
    assert done_events[0].usage is not None
    assert done_events[0].usage.input_tokens == 100
    assert done_events[0].usage.output_tokens == 50
    assert done_events[0].usage.cache_hit_tokens == 30


async def test_run_streamed_translates_sdk_events_to_agent_events() -> None:
    # AR-7.3：run_streamed 集成 skill_translator + event_translator + Runner
    from agents import Agent, MCPApprovalRequestItem, RunItemStreamEvent, ToolCallItem
    from openai.types.responses import ResponseFunctionToolCall, ResponseTextDeltaEvent
    from openai.types.responses.response_output_item import McpApprovalRequest

    skill = SkillDeclaration(
        skill_id="file.read",
        risk_level=RiskLevel.LOW,
        description="read file",
        parameters_schema={"type": "object", "properties": {"path": {"type": "string"}}},
    )
    declaration = AgentDeclaration(
        agent_type="implementer",
        default_skill_set=["file.read"],
        system_prompt_template="你是助手",
    )
    prompt = PromptInput(system_prompt="你是助手", task="写代码")

    # 构造 mock SDK 事件流
    from agents import RawResponsesStreamEvent

    raw_event = RawResponsesStreamEvent(
        data=ResponseTextDeltaEvent(
            content_index=0,
            delta="Hello ",
            item_id="msg_1",
            logprobs=[],
            output_index=0,
            sequence_number=1,
            type="response.output_text.delta",
        )
    )

    test_agent = Agent(name="implementer")

    tool_call_item = ToolCallItem(
        agent=test_agent,
        raw_item=ResponseFunctionToolCall(
            arguments=json.dumps({"path": "/tmp/foo"}),
            call_id="call_1",
            name="file.read",
            type="function_call",
        ),
    )

    approval_raw = McpApprovalRequest(
        id="appr_1",
        arguments=json.dumps({"path": "/tmp/foo"}),
        name="git.commit",
        server_label="orbion",
        type="mcp_approval_request",
    )
    approval_item = MCPApprovalRequestItem(agent=test_agent, raw_item=approval_raw)

    sdk_events = [
        raw_event,
        RunItemStreamEvent(name="tool_called", item=tool_call_item),
        RunItemStreamEvent(name="mcp_approval_requested", item=approval_item),
    ]

    class _FakeRunResult:
        def stream_events(self) -> AsyncIterator[Any]:
            async def _gen() -> AsyncIterator[Any]:
                for e in sdk_events:
                    yield e

            return _gen()

        @property
        def context_wrapper(self) -> object:
            wrapper = MagicMock()
            wrapper.usage = MagicMock(
                input_tokens=100,
                output_tokens=50,
                input_tokens_details=MagicMock(cached_tokens=30),
                output_tokens_details=MagicMock(reasoning_tokens=0),
                total_tokens=150,
                requests=1,
            )
            return wrapper

    mock_runner = MagicMock()
    mock_runner.run_streamed = MagicMock(return_value=_FakeRunResult())

    mock_model_provider = MagicMock()
    from agents import Model

    mock_model_provider.get_model = MagicMock(return_value=MagicMock(spec=Model))

    adapter = _build_adapter(model_provider=mock_model_provider)

    from app.biz.agents.adapters.types import AgentRunRequest

    request = AgentRunRequest(
        run_id="r-1",
        agent_declaration=declaration,
        skill_declarations=[skill],
        prompt=prompt,
    )

    from unittest.mock import patch

    with patch("app.biz.agents.adapters.openai.Runner", mock_runner):
        events = [e async for e in adapter.run_streamed(request)]

    kinds = [e.kind.value for e in events]
    assert "text_delta" in kinds
    assert "tool_call" in kinds
    assert "permission_request" in kinds
    assert "done" in kinds

    done = next(e for e in events if e.kind.value == "done")
    assert done.usage is not None
    assert done.usage.input_tokens == 100
    assert done.usage.output_tokens == 50

    perm = next(e for e in events if e.kind.value == "permission_request")
    assert perm.permission_request is not None
    assert perm.permission_request.run_id == "r-1"
    assert perm.permission_request.callback_url == "POST /runs/r-1/permission"


async def test_close_releases_provider_client() -> None:
    # 边界：close() 释放 provider client
    mock_client = MagicMock(spec=AsyncOpenAI)
    mock_client.close = AsyncMock()
    adapter = _build_adapter(provider_client=mock_client)

    await adapter.close()

    mock_client.close.assert_awaited_once()
