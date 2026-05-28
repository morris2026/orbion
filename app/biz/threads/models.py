"""线程与消息模型：ThreadCreate、ThreadResponse、ThreadListItem、MessageCreate、MessageResponse"""

from datetime import datetime

from pydantic import BaseModel, Field


class ThreadCreate(BaseModel):
    title: str = Field(min_length=1, max_length=256)
    type: str = "discussion"


class ThreadResponse(BaseModel):
    id: str
    project_id: str
    title: str
    status: str
    type: str
    created_at: datetime


class ThreadListItem(BaseModel):
    id: str
    title: str
    status: str
    type: str
    has_summary: bool
    pending_plan_count: int
    message_count: int
    created_at: datetime


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=10000)
    request_summary: bool = False


class MessageResponse(BaseModel):
    id: str
    thread_id: str
    participant_id: str
    participant_type: str
    display_name: str
    content: str
    event_type: str
    created_at: datetime
