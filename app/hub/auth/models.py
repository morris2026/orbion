"""认证模型：UserRegister、UserLogin、UserResponse、TokenPayload"""

from pydantic import BaseModel, Field


class UserRegister(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[a-zA-Z0-9_]+$")
    password: str = Field(min_length=8)
    display_name: str = Field(min_length=1, max_length=64)


class UserLogin(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    user_id: str
    username: str
    display_name: str
    access_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    sub: str
    username: str
    exp: int
    iat: int
