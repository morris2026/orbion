"""ClaudeAdapter——Anthropic Claude SDK适配器（MVP实现）"""

from typing import Any, cast

import anthropic
from anthropic.types import MessageParam

from app.biz.agents.adapters._legacy.base import ModelOutput, PromptInput


class ClaudeAdapter:
    """Anthropic Claude SDK适配器——MVP使用"""

    def __init__(self, api_key: str) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)

    async def complete(self, prompt: PromptInput) -> ModelOutput:
        """调用Claude API生成产出"""
        messages = self._build_messages(prompt)
        system = self._build_system(prompt)

        response = await self._client.messages.create(
            model=prompt.model_config_obj.model_id,
            max_tokens=prompt.model_config_obj.max_tokens,
            temperature=prompt.model_config_obj.temperature,
            system=system,
            messages=cast(list[MessageParam], messages),
        )

        # MVP只取第一个text block
        text_blocks = [b for b in response.content if b.type == "text"]
        content = text_blocks[0].text if text_blocks else ""
        return self._parse_output(content)

    def _build_system(self, prompt: PromptInput) -> str:
        """组装系统提示：role/goal/backstory + memory + context"""
        parts = [prompt.system_prompt]
        if prompt.memory:
            parts.append(f"\n## 行为偏好\n{prompt.memory}")
        if prompt.context:
            parts.append(f"\n## 知识上下文\n{prompt.context}")
        return "\n\n".join(parts)

    def _build_messages(self, prompt: PromptInput) -> list[dict[str, Any]]:
        """组装对话消息：history + task
        human→user角色映射，agent→assistant角色映射
        """
        messages: list[dict[str, Any]] = []
        for summary in prompt.history:
            role = "user" if summary.participant_type == "human" else "assistant"
            messages.append({"role": role, "content": summary.content})
        messages.append({"role": "user", "content": prompt.task})
        return messages

    def _parse_output(self, content: str) -> ModelOutput:
        """解析LLM产出——MVP简化：不做复杂JSON解析，Agent backstory约定输出格式"""
        return ModelOutput(content=content)
