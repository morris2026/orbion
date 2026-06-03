"""AgentMemory——层次化记忆管理（本地文件系统）"""

from pathlib import Path


class AgentMemory:
    """Agent层次化记忆管理——MVP存储在本地文件系统"""

    def __init__(self, base_path: str) -> None:
        """base_path是memory.md文件存储根目录（设计文档1.6第8.3节）"""
        self._base = Path(base_path).resolve()
        self._base.mkdir(parents=True, exist_ok=True)

    def _resolve_safe_path(self, path: str) -> Path:
        """解析路径并验证不越界——防止路径遍历攻击"""
        resolved = (self._base / path / "memory.md").resolve()
        if not str(resolved).startswith(str(self._base)):
            raise ValueError(f"路径越界: {path}")
        return resolved

    def load_memory_chain(self, project_id: str, agent_type: str, correlation_id: str | None = None) -> str:
        """按层次加载memory.md：平台→项目→Agent→任务。
        后加载覆盖前面的设置（类似CSS层叠）——拼接所有层级内容。
        """
        parts = [
            self.read_memory("platform"),
            self.read_memory(f"project/{project_id}"),
            self.read_memory(f"project/{project_id}/agents/{agent_type}"),
        ]
        if correlation_id:
            parts.append(self.read_memory(f"project/{project_id}/tasks/{correlation_id}"))
        return "\n\n".join(p for p in parts if p)

    def read_memory(self, path: str) -> str:
        """读取指定路径的memory.md——不存在返回空字符串"""
        file_path = self._resolve_safe_path(path)
        if not file_path.exists():
            return ""
        return file_path.read_text(encoding="utf-8")

    def write_memory(self, path: str, content: str) -> None:
        """写入指定路径的memory.md——自动创建目录"""
        file_path = self._resolve_safe_path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")

    def reset_agent_memory(self, project_id: str, agent_type: str) -> None:
        """重置特定Agent的记忆——清空内容，不删除文件"""
        file_path = self._resolve_safe_path(f"project/{project_id}/agents/{agent_type}")
        if file_path.exists():
            file_path.write_text("", encoding="utf-8")
