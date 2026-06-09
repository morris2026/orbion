"""认证模型：注册、登录、审批、JWT payload"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class UserRegister(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[a-zA-Z0-9_]+$")
    password: str = Field(min_length=8)
    display_name: str = Field(min_length=1, max_length=64)


class UserLogin(BaseModel):
    username: str
    password: str


class User(BaseModel):
    """从JWT解码的用户对象，供FastAPI依赖注入"""

    id: str
    username: str
    display_name: str = ""
    is_admin: bool = False


class UserResponse(BaseModel):
    """登录成功响应：active用户返回JWT"""

    user_id: str
    username: str
    display_name: str
    access_token: str
    token_type: str = "bearer"


class RegistrationResponse(BaseModel):
    """注册响应：根据RegistrationPolicy决策返回不同内容"""

    user_id: str
    username: str
    display_name: str
    status: str  # "pending" 或 "active"
    access_token: str | None = None  # 仅active状态时有值
    token_type: str | None = None  # 仅active状态时有值
    message: str = ""


class RegistrationDecision(BaseModel):
    """RegistrationPolicy评估结果"""

    status: Literal["pending", "active"]  # MVP: pending（首个用户active）
    is_admin: bool = False  # 仅第一个用户True
    message: str = ""


class PendingUserResponse(BaseModel):
    """待审批用户列表项"""

    user_id: str
    username: str
    display_name: str
    status: str = "pending"
    created_at: datetime


class ApprovalResponse(BaseModel):
    """审批/拒绝操作响应"""

    user_id: str
    username: str
    display_name: str | None = None
    status: str  # "active" 或 "rejected"
    reason: str | None = None  # 仅拒绝时有值


class RejectionRequest(BaseModel):
    """拒绝注册请求体"""

    reason: str | None = None


class UserListItem(BaseModel):
    """用户列表/搜索结果中的active用户项"""

    user_id: str
    username: str
    display_name: str
    status: str = "active"
    created_at: datetime


class TokenPayload(BaseModel):
    sub: str  # user_id
    username: str
    display_name: str = ""
    is_admin: bool = False
    iss: str = "orbion"
    exp: int
    iat: int
