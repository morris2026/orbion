"""EventType枚举、Event模型、EventPayload schema"""

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class EventType(StrEnum):
    """8个MVP事件类型"""

    DiscussionMessageCreated = "DiscussionMessageCreated"
    DiscussionSummaryGenerated = "DiscussionSummaryGenerated"
    ExecutionPlanProposed = "ExecutionPlanProposed"
    ExecutionPlanApproved = "ExecutionPlanApproved"
    ExecutionPlanRejected = "ExecutionPlanRejected"
    TaskOutputGenerated = "TaskOutputGenerated"
    TaskOutputApproved = "TaskOutputApproved"
    TaskOutputRevisionRequested = "TaskOutputRevisionRequested"


class Event(BaseModel):
    """事件模型，与event_log表字段一一对应"""

    event_id: str
    project_id: str
    event_type: str
    participant_id: str
    participant_type: Literal["human", "agent"]
    payload: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str
    causation_id: str | None = None
    created_at: datetime | None = None


# -- EventPayload schemas --


class DiscussionMessageCreatedPayload(BaseModel):
    """DiscussionMessageCreated payload"""

    thread_id: str
    content: str
    request_summary: bool = False


class DiscussionSummaryGeneratedPayload(BaseModel):
    """DiscussionSummaryGenerated payload"""

    thread_id: str
    summary_id: str
    consensus_points: list[str]
    divergence_points: list[str]
    action_items: list[str]
    knowledge_references: list[str]


class PlanTaskItem(BaseModel):
    """ExecutionPlanProposed中的单个任务"""

    task_id: str
    type: str
    description: str
    dependencies: list[str] = Field(default_factory=list)
    priority: Literal["high", "medium", "low"]


class ExecutionPlanProposedPayload(BaseModel):
    """ExecutionPlanProposed payload"""

    plan_id: str
    thread_id: str
    tasks: list[PlanTaskItem]


class ExecutionPlanApprovedPayload(BaseModel):
    """ExecutionPlanApproved payload"""

    plan_id: str
    approved_tasks: list[str]
    modifications: dict[str, dict[str, Any]] | None = None


class ExecutionPlanRejectedPayload(BaseModel):
    """ExecutionPlanRejected payload"""

    plan_id: str
    reason: str
    suggestions: list[str]


class TaskOutputGeneratedPayload(BaseModel):
    """TaskOutputGenerated payload"""

    task_id: str
    plan_id: str
    output_id: str
    output_type: Literal["code", "document"]
    content: str
    diff: str | None = None
    file_paths: list[str] = Field(default_factory=list)


class TaskOutputApprovedPayload(BaseModel):
    """TaskOutputApproved payload"""

    output_id: str
    feedback: str | None = None


class TaskOutputRevisionRequestedPayload(BaseModel):
    """TaskOutputRevisionRequested payload"""

    output_id: str
    task_id: str
    issues: list[str]
    suggestions: list[str]
