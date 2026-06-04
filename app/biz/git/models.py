"""Git模块Pydantic模型"""

from pydantic import BaseModel


class GitLogEntry(BaseModel):
    """git commit摘要"""

    message: str
    hexsha: str
