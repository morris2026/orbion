"""执行计划模型：PlanTask、PlanResponse、PlanApprove、PlanReject"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class PlanTask(BaseModel):
    task_id: str
    type: str
    description: str
    dependencies: list[str] = Field(default_factory=list)
    priority: str
    status: str = "pending"


class PlanResponse(BaseModel):
    id: str
    thread_id: str | None
    status: str
    proposed_by: str
    tasks: list[PlanTask]
    approved_by: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime | None = None


class PlanApprove(BaseModel):
    approved_tasks: list[str] = Field(..., min_length=1)
    modifications: dict[str, dict[str, Any]] | None = None


class PlanReject(BaseModel):
    reason: str = Field(..., min_length=1)
    suggestions: list[str] = Field(default_factory=list)


class PlanApproveResponse(BaseModel):
    plan_id: str
    status: str
    approved_tasks: list[str]
    modifications: dict[str, dict[str, Any]] | None = None


class PlanRejectResponse(BaseModel):
    plan_id: str
    status: str
    reason: str
    suggestions: list[str]
