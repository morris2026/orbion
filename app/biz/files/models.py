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
    mtime: float | None = None  # 文件 mtime（Unix 秒），前端保存时作为 expected_mtime 回传


class WriteFileRequest(BaseModel):
    """写入文件请求（path 由 query param 提供，body 只含 content + 可选合并参数）

    三方合并参数（设计 §5.2.4）：
    - expected_mtime：用户打开文件时记录的 mtime（Unix 秒）；未提供则直接覆盖保存
    - original_content：用户打开时文件的内容；expected_mtime 提供时必填
    """

    content: str
    expected_mtime: float | None = None
    original_content: str | None = None


class FileConflictResponse(BaseModel):
    """409 Conflict 响应——三方合并冲突时返回"""

    path: str
    merged_content: str  # 含冲突标记（<<<<<<< / ||||||| / ======= / >>>>>>>）
    conflict_markers: list[str]  # 每个冲突块的完整标记字符串
    current_mtime: float  # 当前磁盘 mtime，前端可更新后重试
