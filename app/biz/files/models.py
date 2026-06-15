"""文件操作 Pydantic 模型"""

from typing import Literal

from pydantic import BaseModel


class FileNode(BaseModel):
    """文件树节点"""

    path: str
    type: Literal["file", "dir"]
    name: str


class FileContent(BaseModel):
    """文件内容"""

    path: str
    content: str


class WriteFileRequest(BaseModel):
    """写入文件请求（path 由 query param 提供，body 只含 content）"""

    content: str
