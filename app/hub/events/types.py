"""EventType枚举、Event模型、EventPayload schema"""

from datetime import datetime
from enum import StrEnum
from typing import Any, Final, Literal

from pydantic import BaseModel, Field

# Event模型VARCHAR长度约束（与migrations/001_initial.sql event_log表对齐）
EVENT_PROJECT_ID_MAX_LEN: Final[int] = 64
EVENT_PARTICIPANT_ID_MAX_LEN: Final[int] = 64
EVENT_PARTICIPANT_DISPLAY_NAME_MAX_LEN: Final[int] = 64
EVENT_TYPE_MAX_LEN: Final[int] = 64
EVENT_PARTICIPANT_TYPE_MAX_LEN: Final[int] = 8


class EventType(StrEnum):
    """MVP事件类型"""

    ProjectCreated = "ProjectCreated"
    DiscussionMessageCreated = "DiscussionMessageCreated"
    DiscussionSummaryGenerated = "DiscussionSummaryGenerated"
    ExecutionPlanProposed = "ExecutionPlanProposed"
    ExecutionPlanApproved = "ExecutionPlanApproved"
    ExecutionPlanRejected = "ExecutionPlanRejected"
    TaskOutputGenerated = "TaskOutputGenerated"
    TaskOutputApproved = "TaskOutputApproved"
    TaskOutputRevisionRequested = "TaskOutputRevisionRequested"
    MemberAdded = "MemberAdded"
    AgentRegistered = "AgentRegistered"
    UserRegistered = "UserRegistered"
    ProjectDeleted = "ProjectDeleted"


class Event(BaseModel):
    """事件模型，与event_log表字段一一对应"""

    event_id: str
    project_id: str = Field(max_length=EVENT_PROJECT_ID_MAX_LEN)
    event_type: str = Field(max_length=EVENT_TYPE_MAX_LEN)
    participant_id: str = Field(max_length=EVENT_PARTICIPANT_ID_MAX_LEN)
    participant_type: Literal["human", "agent"] = Field(max_length=EVENT_PARTICIPANT_TYPE_MAX_LEN)
    participant_display_name: str = Field(default="", max_length=EVENT_PARTICIPANT_DISPLAY_NAME_MAX_LEN)
    payload: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str
    causation_id: str | None = None
    created_at: datetime | None = None


# -- EventPayload schemas --


class DiscussionMessageCreatedPayload(BaseModel):
    """DiscussionMessageCreated payload — 领域字段 + 投影行主键"""

    thread_id: str
    content: str
    request_summary: bool = False
    message_id: str = ""


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


class ProjectCreatedPayload(BaseModel):
    """ProjectCreated payload — 领域字段 + 默认线程数据"""

    name: str
    description: str | None = None
    default_thread_id: str | None = None
    default_thread_title: str | None = None


class MemberAddedPayload(BaseModel):
    """MemberAdded payload — 纯领域字段：角色"""

    roles: list[str] = Field(default_factory=list)


class AgentRegisteredPayload(BaseModel):
    """AgentRegistered payload — Agent注册领域字段"""

    agent_type: str
    model_id: str
    subscribed_events: list[str] = Field(default_factory=list)
    roles: list[str] = Field(default_factory=list)


class UserRegisteredPayload(BaseModel):
    """UserRegistered payload — 平台级事件，project_id为空字符串"""

    username: str
    display_name: str
    status: Literal["pending", "active", "rejected"]
    is_admin: bool = False


class ProjectDeletedPayload(BaseModel):
    """ProjectDeleted payload — 删除审计用"""

    name: str
