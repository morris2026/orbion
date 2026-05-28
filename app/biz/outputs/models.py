"""产出模型：OutputResponse、OutputApprove、OutputRequestRevision"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class OutputResponse(BaseModel):
    id: str
    task_id: str
    plan_id: str
    output_type: Literal["code", "document"]
    content: str
    diff: str | None = None
    file_paths: list[str] = Field(default_factory=list)
    status: str
    version: int
    created_at: datetime


class OutputApprove(BaseModel):
    feedback: str | None = None


class OutputRequestRevision(BaseModel):
    issues: list[str]
    suggestions: list[str] = Field(default_factory=list)
