"""AgentRuntimeAdapter 类型定义。

设计参考 §6.1（AgentRuntimeAdapter Protocol）/ §6.1.2（StreamChunk）/ §6.5（PromptInput 五字段）
/ §6.6.1（AgentDeclaration）/ §6.6.2（SkillDeclaration + RiskLevel）/ §6.6.3（PermissionDecision）
/ §6.6.6（AuditRecord）/ §6.7.2（UsageInfo + 兜底估算）。

所有类型 SDK 无关，供 Adapter / Runtime / Skill / Audit 共享。步骤 3 仅定义类型骨架，
具体业务字段在后续步骤（5/8/9/10）按需补充。
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from pydantic import BaseModel, Field


class RiskLevel(StrEnum):
    """Skill 风险分级（§6.6.2）：LOW/MEDIUM/HIGH 三级。"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class UsageInfo(BaseModel):
    """模型调用 token 统计（§6.7.2）。

    供方正常返回时 estimated=False；tiktoken 本地估算兜底时 estimated=True。
    cache_hit_tokens 统一缓存命中（Anthropic cache_read_input_tokens / OpenAI cached_tokens）。
    model_name 是供方原始名，便于精确计费对照；供方未返回且未估算时为 None。
    """

    input_tokens: int = 0
    output_tokens: int = 0
    cache_hit_tokens: int = 0
    estimated: bool = False
    model_name: str | None = None

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class ToolCall(BaseModel):
    """模型发起的工具调用请求。"""

    call_id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    """工具调用结果回传给模型。"""

    call_id: str
    output: str = ""
    ok: bool = True
    error: str | None = None


class SkillResult(BaseModel):
    """Orbion Skill handler 统一返回格式（§6.2.1）。

    handler 返回 SkillResult，adapt_handler 包装为 SDK 期望的 JSON 字符串。
    """

    ok: bool
    data: dict[str, Any] | None = None
    reason: str | None = None


class SkillDeclaration(BaseModel):
    """Skill 声明（SDK 无关业务配置，§6.6.2）。

    不含 handler——handler 由 Adapter 注册时绑定（§6.6.2）。
    """

    skill_id: str
    risk_level: RiskLevel
    description: str
    parameters_schema: dict[str, Any]
    allowed_in_worktree_only: bool = True


class AgentDeclaration(BaseModel):
    """Agent 声明（§6.6.1）。"""

    agent_type: str
    default_skill_set: list[str] = Field(default_factory=list)
    optional_skills: list[str] = Field(default_factory=list)
    system_prompt_template: str
    max_turns: int = 25
    output_schema: dict[str, Any] | None = None


class PermissionAction(StrEnum):
    """权限检查决策动作（§6.6.3）。"""

    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"


class PermissionDecision(BaseModel):
    """权限检查决策（§6.6.3）。

    user_approved_at 在用户二次确认 allow 后填充；自动 allow / deny 时为 None。
    """

    action: PermissionAction
    reason: str = ""
    user_approved_at: datetime | None = None


class PermissionRequest(BaseModel):
    """运行时向用户征求权限确认（§6.3.2）。"""

    run_id: str
    callback_url: str
    skill_id: str
    arguments: dict[str, Any] | None = None


class DispatchContext(BaseModel):
    """dispatch 入口上下文（§8.1）。

    跨子系统传递 project_id / task_id / actor 等，SkillPermissionChecker 与 AuditWriter 共享。
    """

    project_id: UUID
    task_id: UUID | None = None
    event_id: UUID | None = None
    actor_user_id: UUID
    worktree_path: str | None = None
    run_kind: str = "dispatch"


class SessionRef(BaseModel):
    """跨进程恢复用的 SDK 会话句柄（§6.7）。

    OpenAI SQLAlchemySession / Claude JSONL transcript 等，stop/resume 时定位续跑上下文。
    """

    session_id: str
    sdk_type: str
    backend: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class AuditStatus(StrEnum):
    """Skill 调用审计状态（§6.6.6）。"""

    SUCCESS = "success"
    FAILED = "failed"
    FORBIDDEN = "forbidden"


class AuditRecord(BaseModel):
    """Skill 调用审计记录（§6.6.6）。

    PgSkillAuditWriter.write 持久化到 skill_calls 表。
    """

    run_id: str
    skill_id: str
    params: dict[str, Any] = Field(default_factory=dict)
    result_summary: str | None = None
    risk_level: RiskLevel
    user_approved_at: datetime | None = None
    status: AuditStatus


@runtime_checkable
class AuditWriter(Protocol):
    """审计写入接口（§6.6.7 部分委托 SDK RunHooks.on_tool_end）。"""

    async def write(self, record: AuditRecord) -> None: ...


@runtime_checkable
class SkillPermissionChecker(Protocol):
    """权限检查器接口（§6.6.3）。

    挂到 SDK permission callback / PreToolUse hook，返回 allow/deny/ask 决策。
    """

    def check(
        self,
        skill_id: str,
        params: dict[str, Any],
        ctx: DispatchContext,
        user_approved: datetime | None = None,
    ) -> PermissionDecision: ...


class ChatMessage(BaseModel):
    """对话历史消息（§6.5.3）。

    role=user/assistant，content 为组装后的字符串。
    """

    role: str
    content: str


class PromptInput(BaseModel):
    """Agent prompt 组装统一输入（§6.5 五字段）。

    system_prompt / context / memory / task / history 五字段，token 预算裁剪由上下文组装层负责。
    """

    system_prompt: str
    context: str = ""
    memory: str = ""
    task: str
    history: list[ChatMessage] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class StreamChunkType(StrEnum):
    """流式产出的块类型（§6.1.2）。"""

    TEXT = "text"
    DONE = "done"
    ERROR = "error"


class StreamChunk(BaseModel):
    """流式产出的单块（§6.1.2）。

    text 块携带 delta，done 块携带完整 usage，error 块携带错误消息。
    done 之前的块 usage 为 None。
    """

    type: StreamChunkType
    delta: str | None = None
    usage: UsageInfo | None = None
    error: str | None = None


class ModelOutput(BaseModel):
    """complete() 同步产出的统一输出。"""

    content: str
    skill_calls: list[ToolCall] | None = None
    reasoning: str | None = None
    usage: UsageInfo | None = None


class AgentEventKind(StrEnum):
    """run_streamed 产出的事件类型（§6.2.2）。"""

    TEXT_DELTA = "text_delta"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    PERMISSION_REQUEST = "permission_request"
    DONE = "done"
    ERROR = "error"


class AgentEvent(BaseModel):
    """run_streamed 产出的运行事件（§6.2.2）。"""

    kind: AgentEventKind
    delta: str | None = None
    tool_call: ToolCall | None = None
    tool_result: ToolResult | None = None
    permission_request: PermissionRequest | None = None
    usage: UsageInfo | None = None
    error: str | None = None


class AgentRunResult(BaseModel):
    """单次 run 的最终结果。"""

    success: bool
    content: str = ""
    usage: UsageInfo | None = None
    artifact_id: UUID | None = None
    error: str | None = None


class AgentRunRequest(BaseModel):
    """run / run_streamed 入参。"""

    run_id: str
    agent_declaration: AgentDeclaration
    skill_declarations: list[SkillDeclaration]
    prompt: PromptInput
    session_ref: SessionRef | None = None
    context: DispatchContext | None = None


class ModelCallError(RuntimeError):
    """模型调用异常（§6.1.2 error chunk 触发）。

    complete() 消费到 error StreamChunk 时抛出，由上层异常体系映射为 HTTP 状态。
    """
