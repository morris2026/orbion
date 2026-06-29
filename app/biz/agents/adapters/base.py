"""AgentRuntimeAdapter Protocol + BaseAdapter 默认实现。

设计参考 §6.1（Protocol 双接口 complete/stream + run/run_streamed）/ §6.1.2（complete 复用 stream
拼接 text delta + 提取 done chunk usage）/ §6.7.2（供方无 usage 时 tiktoken 本地估算兜底）。

BaseAdapter 提供 complete() / run() 默认实现，stream() / run_streamed() / close() 由子类实现。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, AsyncIterator
from typing import Protocol, runtime_checkable

import tiktoken

from app.biz.agents.adapters.types import (
    AgentEvent,
    AgentEventKind,
    AgentRunRequest,
    AgentRunResult,
    ModelCallError,
    ModelOutput,
    PromptInput,
    StreamChunk,
    StreamChunkType,
    UsageInfo,
)


@runtime_checkable
class AgentRuntimeAdapter(Protocol):
    """模型 + Agent SDK 双适配器抽象（§6.1）。

    complete/stream 是 Provider SDK 直调路径（chat / lightweight_call），
    run/run_streamed 是 Agent SDK Runner 路径（dispatch）。
    """

    async def complete(self, prompt: PromptInput) -> ModelOutput:
        """同步产出（轻量调用 / 一次性补全）。"""
        ...

    def stream(self, prompt: PromptInput) -> AsyncIterator[StreamChunk]:
        """流式产出（chat 流式响应）。"""
        ...

    async def run(self, request: AgentRunRequest) -> AgentRunResult:
        """完整 Agent 执行（dispatch 路径，非流式）。"""
        ...

    def run_streamed(self, request: AgentRunRequest) -> AsyncIterator[AgentEvent]:
        """完整 Agent 执行（dispatch 路径，流式事件）。"""
        ...

    async def close(self) -> None:
        """释放底层 SDK client / sessions / MCP 子进程。"""
        ...


class BaseAdapter:
    """Adapter 默认实现基类（§6.1.2）。

    complete() 复用 stream() 拼接 text delta + 提取 done chunk usage；
    供方无 usage 时用 tiktoken 本地估算兜底；
    run() 复用 run_streamed() 拼接事件。
    子类必须实现 stream() / run_streamed() / close()。

    error 处理差异：complete() 消费到 error StreamChunk 时抛 ModelCallError（异常中断），
    run() 消费到 error AgentEvent 时流入 AgentRunResult(success=False, error=...)（终态事件）。
    子类 stream() / run_streamed() 内部若持有底层 HTTP 流，必须在 GeneratorExit 时关闭。
    """

    def __init__(self, model_name: str) -> None:
        self._model_name = model_name

    async def complete(self, prompt: PromptInput) -> ModelOutput:
        text_parts: list[str] = []
        usage: UsageInfo | None = None
        async for chunk in self.stream(prompt):
            if chunk.type is StreamChunkType.TEXT and chunk.delta is not None:
                text_parts.append(chunk.delta)
            elif chunk.type is StreamChunkType.DONE:
                usage = chunk.usage
            elif chunk.type is StreamChunkType.ERROR:
                raise ModelCallError(chunk.error or "model call failed")
        content = "".join(text_parts)
        if usage is None:
            usage = self._estimate_usage(prompt, content)
        return ModelOutput(content=content, usage=usage)

    def _estimate_usage(self, prompt: PromptInput, content: str) -> UsageInfo:
        """供方未返回 usage 时用 tiktoken 本地估算兜底（§6.7.2）。

        未知模型名回退到 cl100k_base 编码；估算结果 estimated=True 供调用方区分。
        """
        try:
            encoding = tiktoken.encoding_for_model(self._model_name)
        except KeyError:
            encoding = tiktoken.get_encoding("cl100k_base")
        prompt_text = prompt.system_prompt + prompt.context + prompt.memory + prompt.task
        for msg in prompt.history:
            prompt_text += msg.content
        return UsageInfo(
            input_tokens=len(encoding.encode(prompt_text)),
            output_tokens=len(encoding.encode(content)),
            estimated=True,
            model_name=self._model_name,
        )

    async def run(self, request: AgentRunRequest) -> AgentRunResult:
        content_parts: list[str] = []
        usage: UsageInfo | None = None
        error: str | None = None
        async for event in self.run_streamed(request):
            if event.kind is AgentEventKind.TEXT_DELTA and event.delta is not None:
                content_parts.append(event.delta)
            elif event.kind is AgentEventKind.DONE:
                usage = event.usage
            elif event.kind is AgentEventKind.ERROR:
                error = event.error or "agent run failed"
        content = "".join(content_parts)
        if error is not None:
            return AgentRunResult(success=False, content=content, usage=usage, error=error)
        return AgentRunResult(success=True, content=content, usage=usage)

    async def stream(self, prompt: PromptInput) -> AsyncGenerator[StreamChunk, None]:
        """子类必须实现为 async generator。"""
        raise NotImplementedError
        yield  # pragma: no cover - 让函数成为 async generator

    async def run_streamed(self, request: AgentRunRequest) -> AsyncGenerator[AgentEvent, None]:
        """子类必须实现为 async generator。"""
        raise NotImplementedError
        yield  # pragma: no cover - 让函数成为 async generator

    async def close(self) -> None:
        """子类按需释放 Provider client / SDK sessions / MCP 子进程。"""
