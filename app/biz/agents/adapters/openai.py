"""OpenAIAgentRuntimeAdapter — openai-agents SDK 适配器（§6.2）。

用 `openai-agents` 包 + `ModelProvider` 抽象覆盖多模型：
- complete/stream：Provider SDK 直调（AsyncOpenAI chat.completions）。MVP 仅支持 openai /
  openai_compat / azure_openai provider；anthropic provider 的 complete/stream 不支持
 （anthropic 模型通过 run_streamed + AnthropicModelProvider 接入，lightweight_call 走 openai 兼容路径）
- run/run_streamed：Agent SDK Runner（ModelProvider 注入，anthropic→AnthropicModelProvider / 其他→OpenAIProvider）

sessions / mcp_configs 按 project_id 隔离（预留字段，步骤 9/10 + MCP 配置层后续注入）。
SkillPermissionChecker 注册为 needs_approval callback（步骤 9 后注入）、AuditWriter 注册为
RunHooks.on_tool_end（步骤 10 后注入）、mcp_servers.json 加载（后续 MCP 配置层步骤）、
Runner.run_streamed 的 max_turns/session/context 注入（步骤 12 dispatch 组装时传入）均推迟。
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from typing import Any, cast

from agents import Agent, ModelProvider, OpenAIProvider, Runner
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam
from openai.types.completion_usage import CompletionUsage
from pydantic import BaseModel

from app.biz.agents.adapters.anthropic_provider import AnthropicModelProvider
from app.biz.agents.adapters.base import BaseAdapter
from app.biz.agents.adapters.event_translator import translate_openai_stream_events
from app.biz.agents.adapters.factory import AdapterFactory, UserModelProtocol
from app.biz.agents.adapters.skill_translator import translate_skill_to_function_tool
from app.biz.agents.adapters.types import (
    AgentEvent,
    AgentRunRequest,
    PromptInput,
    SkillResult,
    StreamChunk,
    StreamChunkType,
    UsageInfo,
)
from app.biz.user_models.encryption import decrypt_api_key

logger = logging.getLogger(__name__)


class _StubParams(BaseModel):
    """步骤 7 占位参数类型，步骤 8 替换为真实 skill params_type。"""


_NOT_IMPL_ANTHROPIC_MSG = (
    "anthropic provider 的 complete/stream MVP 不支持 —— "
    "Anthropic 模型通过 run_streamed + AnthropicModelProvider 接入（§6.3.1）。"
    "lightweight_call 请用 openai/openai_compat provider。"
)


def openai_usage_to_usage_info(usage: CompletionUsage, model_name: str) -> UsageInfo:
    """OpenAI CompletionUsage → Orbion UsageInfo（§6.7.2）。

    prompt_tokens → input_tokens；completion_tokens → output_tokens；
    prompt_tokens_details.cached_tokens → cache_hit_tokens（None 兜底 0）。
    """
    cached = 0
    if usage.prompt_tokens_details and usage.prompt_tokens_details.cached_tokens:
        cached = usage.prompt_tokens_details.cached_tokens
    return UsageInfo(
        input_tokens=usage.prompt_tokens,
        output_tokens=usage.completion_tokens,
        cache_hit_tokens=cached,
        estimated=False,
        model_name=model_name,
    )


def build_model_provider(
    provider: str,
    api_key: str,
    base_url: str | None,
) -> tuple[ModelProvider, AsyncAnthropic | None]:
    """按 provider 路由构造 ModelProvider（§6.4 + §6.7.3）。

    anthropic → AnthropicModelProvider（返回 Anthropic client 供 adapter close 释放）；
    openai / azure_openai / openai_compat → OpenAIProvider（无额外 client）。
    MVP 所有 provider 都走 OpenAIAgentRuntimeAdapter（Anthropic 模型通过 AnthropicModelProvider 接入）。
    """
    if provider == "anthropic":
        anthropic_client = AsyncAnthropic(api_key=api_key, base_url=base_url)
        return AnthropicModelProvider(anthropic_client), anthropic_client
    return OpenAIProvider(api_key=api_key, base_url=base_url), None


class OpenAIAgentRuntimeAdapter(BaseAdapter):
    """openai-agents SDK 适配器（§6.2）。"""

    def __init__(
        self,
        user_model: UserModelProtocol,
        provider_client: AsyncOpenAI,
        model_provider: ModelProvider,
        extra_closeables: list[Any] | None = None,
    ) -> None:
        super().__init__(model_name=user_model.model_name)
        self._user_model = user_model
        self._provider_client = provider_client
        self._model_provider = model_provider
        self._extra_closeables = list(extra_closeables) if extra_closeables else []
        self._sessions: dict[str, Any] = {}
        self._mcp_configs: dict[str, list[Any]] = {}

    async def stream(self, prompt: PromptInput) -> AsyncGenerator[StreamChunk, None]:
        """Provider SDK 直调流式（§6.1.2）。MVP 仅支持 openai/openai_compat provider。"""
        if self._user_model.provider == "anthropic":
            raise NotImplementedError(_NOT_IMPL_ANTHROPIC_MSG)
            yield  # pragma: no cover
        messages = self._build_messages(prompt)
        stream = await self._provider_client.chat.completions.create(
            model=self._model_name,
            messages=cast("list[ChatCompletionMessageParam]", messages),
            stream=True,
            stream_options={"include_usage": True},
        )
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield StreamChunk(
                    type=StreamChunkType.TEXT,
                    delta=chunk.choices[0].delta.content,
                )
            if chunk.usage:
                yield StreamChunk(
                    type=StreamChunkType.DONE,
                    usage=openai_usage_to_usage_info(chunk.usage, self._model_name),
                )

    async def run_streamed(self, request: AgentRunRequest) -> AsyncGenerator[AgentEvent, None]:
        """Agent SDK Runner 流式（§6.2）+ event_translator 转换。"""
        agent = _build_sdk_agent(request, self._model_provider, self._model_name)
        run = Runner.run_streamed(
            starting_agent=agent,
            input=request.prompt.task,
        )

        async def get_usage() -> UsageInfo | None:
            wrapper = run.context_wrapper
            sdk_usage = wrapper.usage
            if sdk_usage is None:
                return None
            cached = 0
            if sdk_usage.input_tokens_details:
                cached = sdk_usage.input_tokens_details.cached_tokens or 0
            return UsageInfo(
                input_tokens=sdk_usage.input_tokens,
                output_tokens=sdk_usage.output_tokens,
                cache_hit_tokens=cached,
                estimated=False,
                model_name=self._model_name,
            )

        async for event in translate_openai_stream_events(
            run.stream_events(),
            request.run_id,
            get_usage,
        ):
            yield event

    async def close(self) -> None:
        """释放 Provider client + extra closeables（含 Anthropic client）+ sessions + mcp_configs。

        单个资源 close() 抛异常不中断后续释放（与 AdapterFactory.close_all 语义一致）。
        """
        errors: list[BaseException] = []
        await _safe_close(self._provider_client, errors)
        for closeable in self._extra_closeables:
            await _safe_close(closeable, errors)
        for session in self._sessions.values():
            await _safe_close(session, errors)
        for mcp_list in self._mcp_configs.values():
            for mcp in mcp_list:
                await _safe_close(mcp, errors)
        if errors:
            raise errors[0]

    def _build_messages(self, prompt: PromptInput) -> list[dict[str, str]]:
        """组装 OpenAI chat messages（system + history + task，含 context/memory 拼进 system）。"""
        messages: list[dict[str, str]] = []
        system_parts: list[str] = [prompt.system_prompt]
        if prompt.context:
            system_parts.append(f"[context]\n{prompt.context}")
        if prompt.memory:
            system_parts.append(f"[memory]\n{prompt.memory}")
        if any(system_parts):
            messages.append({"role": "system", "content": "\n\n".join(system_parts)})
        for msg in prompt.history:
            messages.append({"role": msg.role, "content": msg.content})
        messages.append({"role": "user", "content": prompt.task})
        return messages


async def _safe_close(target: object, errors: list[BaseException]) -> None:
    """调用 target.close()（若存在），异常收集到 errors 不中断。"""
    close = getattr(target, "close", None)
    if close is None:
        return
    try:
        result = close()
        if hasattr(result, "__await__"):
            await result
    except BaseException as exc:  # noqa: BLE001
        errors.append(exc)


def _build_sdk_agent(
    request: AgentRunRequest,
    model_provider: ModelProvider,
    model_name: str,
) -> Agent[Any]:
    """把 AgentDeclaration + SkillDeclaration 翻译为 SDK Agent + FunctionTool。

    步骤 7 用 stub handler + _StubParams（步骤 8 实现真实 skill handler 绑定后替换）。
    """
    tools: list[Any] = []
    for skill in request.skill_declarations:
        tools.append(translate_skill_to_function_tool(skill, _stub_handler, _StubParams))

    return Agent(
        name=request.agent_declaration.agent_type,
        instructions=request.prompt.system_prompt,
        tools=tools,
        model=model_provider.get_model(model_name),
    )


async def _stub_handler(_params: _StubParams) -> SkillResult:
    """占位 handler，步骤 8 替换为真实 skill handler 绑定。"""
    return SkillResult(ok=True)


class OrbionAdapterFactory(AdapterFactory):
    """Orbion 具体 AdapterFactory：按 provider 路由创建 OpenAIAgentRuntimeAdapter。"""

    async def _build(self, user_model: UserModelProtocol) -> OpenAIAgentRuntimeAdapter:
        api_key = decrypt_api_key(user_model.api_key_enc).decode()
        provider_client = AsyncOpenAI(
            api_key=api_key,
            base_url=user_model.base_url,
        )
        model_provider, anthropic_client = build_model_provider(
            provider=user_model.provider,
            api_key=api_key,
            base_url=user_model.base_url,
        )
        extra_closeables: list[Any] = []
        if anthropic_client is not None:
            extra_closeables.append(anthropic_client)
        return OpenAIAgentRuntimeAdapter(
            user_model,
            provider_client,
            model_provider,
            extra_closeables=extra_closeables,
        )
