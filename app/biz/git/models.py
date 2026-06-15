"""Git模块Pydantic模型"""

from pydantic import BaseModel, Field


class GitLogEntry(BaseModel):
    """git commit摘要"""

    message: str
    hexsha: str


class GitFileStatus(BaseModel):
    """git status 文件条目"""

    path: str
    status: str


class GitStatusResult(BaseModel):
    """git status 结果"""

    staged: list[GitFileStatus]
    changes: list[GitFileStatus]


class StageRequest(BaseModel):
    """stage/unstage 请求"""

    paths: list[str] = Field(..., min_length=1)


class CommitRequest(BaseModel):
    """commit 请求"""

    message: str = Field(..., min_length=1)
