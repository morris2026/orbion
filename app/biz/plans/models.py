"""执行计划模型：PlanTask、PlanResponse、PlanApprove、PlanReject"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class PlanTask(BaseModel):
    task_id: str
    type: str
    description: str
    dependencies: list[str] = Field(default_factory=list)
    priority: Literal["high", "medium", "low"]
    status: str = "pending"


class PlanResponse(BaseModel):
    id: str
    thread_id: str | None
    status: str
    proposed_by: str
    tasks: list[PlanTask]
    created_at: datetime


class PlanApprove(BaseModel):
    approved_tasks: list[str]
    modifications: dict[str, dict[str, Any]] | None = None


class PlanReject(BaseModel):
    reason: str
    suggestions: list[str] = Field(default_factory=list)
