"""项目模型：ProjectCreate、ProjectResponse、ProjectListItem、MemberAdd、MemberResponse"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ProjectCreate(BaseModel):
    name: str = Field(max_length=128)
    description: str | None = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 1:
            raise ValueError("项目名称不能为空")
        return v


class ProjectResponse(BaseModel):
    id: str
    name: str
    description: str | None
    tenant_id: str = "default"
    default_thread_id: str | None = None
    created_at: datetime


class ProjectListItem(BaseModel):
    id: str
    name: str
    description: str | None
    role: str
    default_thread_id: str | None = None
    created_at: datetime


class MemberAdd(BaseModel):
    user_id: str = Field(min_length=1)
    role: Literal["owner", "admin", "member", "viewer"]


class MemberResponse(BaseModel):
    participant_id: str
    project_id: str
    type: str
    display_name: str
    role: str
    agent_type: str | None = None


class MemberListItem(BaseModel):
    participant_id: str
    project_id: str
    type: str
    display_name: str
    role: str
    agent_type: str | None = None
