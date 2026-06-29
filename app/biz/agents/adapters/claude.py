"""ClaudeAgentRuntimeAdapter — Claude Agent SDK 适配器预留接口（§6.3）。

MVP 阶段不实现 Claude Agent SDK 适配器。Anthropic 模型当前通过 OpenAIAgentRuntimeAdapter +
AnthropicModelProvider 接入（§6.3.1）。本类仅保留接口占位，调用任何方法均 raise NotImplementedError，
防止误用。未来启用 Claude Agent SDK 独有能力（subagents / can_use_tool / PreToolUse hook 等）时替换。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from app.biz.agents.adapters.base import BaseAdapter
from app.biz.agents.adapters.types import AgentEvent, AgentRunRequest, PromptInput, StreamChunk

_NOT_IMPL_MSG = (
    "ClaudeAgentRuntimeAdapter 未实现 —— "
    "Anthropic 模型当前通过 OpenAIAgentRuntimeAdapter + AnthropicModelProvider 接入（§6.3.1）。"
    "未来启用 Claude Agent SDK 独有能力时替换本类。"
)


class ClaudeAgentRuntimeAdapter(BaseAdapter):
    """Claude Agent SDK 适配器预留（§6.3）。

    所有方法 raise NotImplementedError，model_name 占位值不会被使用。
    """

    def __init__(self) -> None:
        super().__init__(model_name="claude-stub")

    async def stream(self, prompt: PromptInput) -> AsyncGenerator[StreamChunk, None]:
        raise NotImplementedError(_NOT_IMPL_MSG)
        yield  # pragma: no cover - 让函数成为 async generator

    async def run_streamed(self, request: AgentRunRequest) -> AsyncGenerator[AgentEvent, None]:
        raise NotImplementedError(_NOT_IMPL_MSG)
        yield  # pragma: no cover - 让函数成为 async generator

    async def complete(self, prompt: PromptInput) -> None:  # type: ignore[override]
        raise NotImplementedError(_NOT_IMPL_MSG)
