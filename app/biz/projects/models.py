"""项目模型：ProjectCreate、ProjectResponse、ProjectListItem、MemberAdd、MemberResponse"""

from datetime import datetime

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None


class ProjectResponse(BaseModel):
    id: str
    name: str
    description: str | None
    tenant_id: str = "default"
    created_at: datetime


class ProjectListItem(BaseModel):
    id: str
    name: str
    description: str | None
    role: str
    created_at: datetime


class MemberAdd(BaseModel):
    user_id: str
    role: str


class MemberResponse(BaseModel):
    participant_id: str
    project_id: str
    type: str
    display_name: str
    role: str
