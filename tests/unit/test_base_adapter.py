"""BaseAdapter 默认实现 UT：AR-3.1–AR-3.4。

验证 complete() 内部复用 stream() 拼接 text delta、done chunk usage 提取、
供方无 usage 时 tiktoken 本地估算兜底、error chunk 触发 ModelCallError。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest

from app.biz.agents.adapters.base import BaseAdapter
from app.biz.agents.adapters.types import (
    ModelCallError,
    ModelOutput,
    PromptInput,
    StreamChunk,
    StreamChunkType,
    UsageInfo,
)


class FakeAgentRuntimeAdapter(BaseAdapter):
    """按脚本 yield StreamChunk 的可控 Adapter。"""

    def __init__(self, script: list[StreamChunk], model_name: str = "gpt-4o") -> None:
        super().__init__(model_name=model_name)
        self._script = script

    async def stream(self, prompt: PromptInput) -> AsyncGenerator[StreamChunk, None]:
        for chunk in self._script:
            yield chunk


def _build_prompt() -> PromptInput:
    return PromptInput(system_prompt="你是助手", task="写一句话")


async def test_complete_concats_text_deltas_and_extracts_done_usage() -> None:
    # AR-3.1 + AR-3.2：complete() 拼接 text delta，从 done chunk 提取 usage
    usage = UsageInfo(input_tokens=10, output_tokens=5, model_name="gpt-4o")
    script = [
        StreamChunk(type=StreamChunkType.TEXT, delta="Hello "),
        StreamChunk(type=StreamChunkType.TEXT, delta="World"),
        StreamChunk(type=StreamChunkType.DONE, usage=usage),
    ]
    adapter = FakeAgentRuntimeAdapter(script)

    output = await adapter.complete(_build_prompt())

    assert isinstance(output, ModelOutput)
    assert output.content == "Hello World"
    assert output.usage is usage


async def test_text_chunk_usage_is_none_and_done_chunk_carries_usage() -> None:
    # AR-3.2：done 之前 chunk.usage 为 None；done chunk.usage 完整
    usage = UsageInfo(input_tokens=10, output_tokens=5, model_name="gpt-4o")
    script = [
        StreamChunk(type=StreamChunkType.TEXT, delta="a"),
        StreamChunk(type=StreamChunkType.TEXT, delta="b"),
        StreamChunk(type=StreamChunkType.TEXT, delta="c"),
        StreamChunk(type=StreamChunkType.DONE, usage=usage),
    ]
    adapter = FakeAgentRuntimeAdapter(script)

    output = await adapter.complete(_build_prompt())

    for chunk in script[:-1]:
        assert chunk.usage is None
    assert script[-1].usage is usage
    assert output.usage is usage


async def test_complete_estimates_usage_when_provider_returns_none() -> None:
    # AR-3.3：done chunk 不含 usage → tiktoken 本地估算兜底
    script = [
        StreamChunk(type=StreamChunkType.TEXT, delta="你好世界"),
        StreamChunk(type=StreamChunkType.DONE, usage=None),
    ]
    adapter = FakeAgentRuntimeAdapter(script, model_name="gpt-4o")

    output = await adapter.complete(_build_prompt())

    assert output.usage is not None
    assert output.usage.estimated is True
    assert output.usage.input_tokens > 0
    assert output.usage.output_tokens > 0
    assert output.usage.model_name == "gpt-4o"


async def test_complete_estimates_usage_falls_back_to_cl100k_for_unknown_model() -> None:
    # AR-3.3：未知模型名 tiktoken.encoding_for_model 抛 KeyError → 回退 cl100k_base
    script = [
        StreamChunk(type=StreamChunkType.TEXT, delta="hello world"),
        StreamChunk(type=StreamChunkType.DONE, usage=None),
    ]
    adapter = FakeAgentRuntimeAdapter(script, model_name="unknown-xyz-model")

    output = await adapter.complete(_build_prompt())

    assert output.usage is not None
    assert output.usage.estimated is True
    assert output.usage.input_tokens > 0
    assert output.usage.output_tokens > 0
    assert output.usage.model_name == "unknown-xyz-model"


async def test_complete_raises_model_call_error_on_error_chunk() -> None:
    # AR-3.4：error chunk 触发 ModelCallError，消息含原文
    script = [
        StreamChunk(type=StreamChunkType.TEXT, delta="partial"),
        StreamChunk(type=StreamChunkType.ERROR, error="upstream 5xx"),
    ]
    adapter = FakeAgentRuntimeAdapter(script)

    with pytest.raises(ModelCallError, match="upstream 5xx"):
        await adapter.complete(_build_prompt())
