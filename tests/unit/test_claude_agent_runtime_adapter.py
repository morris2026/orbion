"""ClaudeAgentRuntimeAdapter UT：AR-7.4。"""

from __future__ import annotations

import pytest

from app.biz.agents.adapters.claude import ClaudeAgentRuntimeAdapter
from app.biz.agents.adapters.types import AgentDeclaration, AgentRunRequest, PromptInput


async def test_run_streamed_raises_not_implemented() -> None:
    # AR-7.4：ClaudeAgentRuntimeAdapter raise NotImplementedError
    adapter = ClaudeAgentRuntimeAdapter()
    declaration = AgentDeclaration(
        agent_type="implementer",
        default_skill_set=[],
        system_prompt_template="你是助手",
    )
    request = AgentRunRequest(
        run_id="r-1",
        agent_declaration=declaration,
        skill_declarations=[],
        prompt=PromptInput(system_prompt="你是助手", task="hi"),
    )

    with pytest.raises(NotImplementedError) as exc_info:
        async for _ in adapter.run_streamed(request):
            pass

    msg = str(exc_info.value)
    assert "ClaudeAgentRuntimeAdapter 未实现" in msg
    assert "Anthropic 模型当前通过 OpenAIAgentRuntimeAdapter + AnthropicModelProvider 接入" in msg


async def test_stream_raises_not_implemented() -> None:
    # 边界：stream 也 raise NotImplementedError
    adapter = ClaudeAgentRuntimeAdapter()

    with pytest.raises(NotImplementedError):
        async for _ in adapter.stream(PromptInput(system_prompt="sys", task="hi")):
            pass


async def test_complete_raises_not_implemented() -> None:
    # 边界：complete 也 raise NotImplementedError
    adapter = ClaudeAgentRuntimeAdapter()

    with pytest.raises(NotImplementedError):
        await adapter.complete(PromptInput(system_prompt="sys", task="hi"))
