"""AgentMemory——层次化记忆管理（本地文件系统）"""

from __future__ import annotations

from pathlib import Path

from app.config import Settings


class AgentMemory:
    """Agent层次化记忆管理——三层记忆（平台→项目→Agent），存储在本地文件系统"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._root = Path(settings.root_dir).resolve()

    def _validate_path(self, path: Path) -> Path:
        """解析路径并验证不越界——防止路径遍历攻击"""
        resolved = path.resolve()
        if not resolved.is_relative_to(self._root):
            raise ValueError(f"路径越界: {path}")
        return resolved

    def load_memory_chain(self, project_id: str, agent_type: str) -> str:
        """按层次加载memory.md：平台→项目→Agent，用\\n\\n拼接所有层级内容"""
        parts = [
            self.read_memory(self._settings.platform_memory_path),
            self.read_memory(self._settings.project_memory_path(project_id)),
            self.read_memory(self._settings.agent_memory_path(project_id, agent_type)),
        ]
        return "\n\n".join(p for p in parts if p)

    def read_memory(self, path: Path) -> str:
        """读取指定路径的memory.md——不存在返回空字符串"""
        file_path = self._validate_path(path)
        if not file_path.exists():
            return ""
        return file_path.read_text(encoding="utf-8")

    def write_memory(self, path: Path, content: str) -> None:
        """写入指定路径的memory.md——自动创建目录"""
        file_path = self._validate_path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")

    def reset_agent_memory(self, project_id: str, agent_type: str) -> None:
        """重置特定Agent的记忆——清空内容，不删除文件"""
        file_path = self._validate_path(self._settings.agent_memory_path(project_id, agent_type))
        if file_path.exists():
            file_path.write_text("", encoding="utf-8")
