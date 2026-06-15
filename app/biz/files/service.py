"""文件操作服务 — 文件树/读取/保存"""

import logging
import os
from pathlib import Path

from app.biz.files.models import FileNode
from app.config import Settings

logger = logging.getLogger(__name__)


class FileService:
    """项目仓库文件操作：目录树遍历、文件读取/保存"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _repo_path(self, project_id: str, repo_name: str) -> Path:
        return self._settings.project_repo_path(project_id, repo_name).resolve()

    def _validate_path(self, repo_root: Path, file_path: str) -> Path:
        full = (repo_root / file_path).resolve()
        if not full.is_relative_to(repo_root):
            raise ValueError(f"路径越界: {file_path}")
        return full

    def get_file_tree(self, project_id: str, repo_name: str) -> list[FileNode]:
        repo_root = self._repo_path(project_id, repo_name)
        if not repo_root.exists():
            return []
        result: list[FileNode] = []
        for dirpath, dirnames, filenames in os.walk(repo_root):
            dirnames[:] = [d for d in dirnames if d != ".git"]
            rel_dir = Path(dirpath).relative_to(repo_root)
            for name in filenames:
                rel = str(rel_dir / name) if str(rel_dir) != "." else name
                result.append(FileNode(path=rel, type="file", name=name))
            for name in dirnames:
                rel = str(rel_dir / name) if str(rel_dir) != "." else name
                result.append(FileNode(path=rel, type="dir", name=name))
        return result

    def read_file(self, project_id: str, repo_name: str, file_path: str, *, ref: str | None = None) -> str:
        repo_root = self._repo_path(project_id, repo_name)
        self._validate_path(repo_root, file_path)
        if ref == "HEAD":
            return self._read_head_version(repo_root, file_path)
        full = (repo_root / file_path).resolve()
        if not full.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")
        return full.read_text(encoding="utf-8")

    def _read_head_version(self, repo_root: Path, file_path: str) -> str:
        try:
            import git

            repo = git.Repo(str(repo_root))
            if repo.head.is_valid():
                try:
                    blob = repo.head.commit.tree / file_path
                    return str(blob.data_stream.read().decode("utf-8"))
                except (KeyError, TypeError):
                    return ""
            return ""
        except Exception:
            logger.debug("读取 HEAD 版本失败: repo=%s path=%s", repo_root, file_path, exc_info=True)
            return ""

    def write_file(self, project_id: str, repo_name: str, file_path: str, content: str) -> None:
        repo_root = self._repo_path(project_id, repo_name)
        full = self._validate_path(repo_root, file_path)
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding="utf-8")
