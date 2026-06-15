"""仓库管理 Pydantic 模型"""

from pydantic import BaseModel


class RepoInfo(BaseModel):
    """仓库信息"""

    name: str


class AddRepoRequest(BaseModel):
    """添加仓库请求"""

    url: str | None = None
    name: str | None = None
