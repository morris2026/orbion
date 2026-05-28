"""Agent模型：AgentCreate、AgentResponse、AgentStatus"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class AgentCreate(BaseModel):
    agent_type: Literal["summary", "decompose", "execute"]
    model_id: str
    display_name: str


class AgentResponse(BaseModel):
    participant_id: str
    project_id: str
    type: str = "agent"
    display_name: str
    agent_type: str
    model_id: str
    status: Literal["idle", "running", "error"]
    subscribed_events: list[str]
    roles: int


class AgentStatus(BaseModel):
    agent_id: str
    status: Literal["idle", "running", "error"]
    current_task: str | None = None
    completed_count: int
    error_count: int
    last_execution_at: datetime | None = None
