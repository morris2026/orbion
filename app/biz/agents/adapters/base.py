"""ModelAdapter Protocol定义——ClaudeAdapter在步骤13实现"""

from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel


class ModelConfig(BaseModel):
    """模型配置，每个Agent有独立的模型配置"""

    model_id: str
    temperature: float = 0.5
    max_tokens: int = 4096
    top_p: float = 1.0


class EventSummary(BaseModel):
    """事件摘要，用于构建Agent上下文历史"""

    event_type: str
    participant_id: str
    participant_type: str
    content: str
    created_at: datetime


class PromptInput(BaseModel):
    """Agent prompt组装的统一输入格式"""

    system_prompt: str
    context: str = ""
    memory: str = ""
    task: str
    history: list[EventSummary] = []
    model_config_obj: ModelConfig
    metadata: dict[str, Any] = {}


class SkillCall(BaseModel):
    """Agent对Skill的调用请求"""

    name: str
    arguments: dict[str, Any]


class ModelOutput(BaseModel):
    """LLM产出的统一输出格式"""

    content: str
    skill_calls: list[SkillCall] | None = None
    reasoning: str | None = None


@runtime_checkable
class ModelAdapter(Protocol):
    """模型适配器抽象接口"""

    async def complete(self, prompt: PromptInput) -> ModelOutput: ...
