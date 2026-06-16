import enum
from datetime import datetime

from pydantic import BaseModel, Field


class CredentialType(enum.StrEnum):
    GITHUB = "github"


class CreateCredentialRequest(BaseModel):
    type: CredentialType
    name: str = Field(max_length=64)
    token: str = Field(max_length=512)


class Credential(BaseModel):
    id: str
    type: CredentialType
    name: str
    token: str
    created_at: datetime = Field(default_factory=datetime.now)


class CredentialResponse(BaseModel):
    """API 返回的凭据，不含 token"""

    id: str
    type: CredentialType
    name: str
    created_at: datetime
