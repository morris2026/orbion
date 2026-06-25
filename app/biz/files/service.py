"""文件操作服务 — 文件树/读取/保存"""

import logging
import math
import os
import tempfile
from pathlib import Path

from app.biz.files.models import FileNode
from app.biz.git.git_service import GitCommandService
from app.config import Settings

logger = logging.getLogger(__name__)


class FileService:
    """项目仓库文件操作：目录树遍历、文件读取/保存"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._git = GitCommandService()

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
        """读取文件内容（向后兼容入口）"""
        content, _ = self.read_file_with_mtime(project_id, repo_name, file_path, ref=ref)
        return content

    def read_file_with_mtime(
        self, project_id: str, repo_name: str, file_path: str, *, ref: str | None = None
    ) -> tuple[str, float | None]:
        """读取文件内容 + 当前 mtime（前端打开文件时记录 mtime，保存时回传 expected_mtime）

        ref='HEAD' 时 mtime 为 None（HEAD 版本无磁盘 mtime 概念）。
        """
        repo_root = self._repo_path(project_id, repo_name)
        self._validate_path(repo_root, file_path)
        if ref == "HEAD":
            return self._read_head_version(repo_root, file_path), None
        full = (repo_root / file_path).resolve()
        if not full.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")
        try:
            content = full.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            # 二进制文件无法作为文本返回——前端编辑器不支持，返回空内容 + warning
            # Why：与 write_file_with_merge 的二进制处理对称（保存端也退化为不 merge）
            logger.warning("文件 %s 非文本，返回空内容", file_path)
            content = ""
        mtime = os.path.getmtime(full)
        return content, mtime

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
        """直接覆盖保存（向后兼容入口）"""
        repo_root = self._repo_path(project_id, repo_name)
        full = self._validate_path(repo_root, file_path)
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding="utf-8")

    def write_file_with_merge(
        self,
        project_id: str,
        repo_name: str,
        file_path: str,
        content: str,
        expected_mtime: float | None = None,
        original_content: str | None = None,
    ) -> tuple[str, float]:
        """带 mtime 检测 + 三方合并的保存（设计 §5.2）

        - expected_mtime 为 None：直接覆盖保存（legacy 行为）
        - expected_mtime 与当前 mtime 一致：直接保存
        - expected_mtime 与当前 mtime 不一致：执行三方合并
          - 合并成功：原子写入合并结果（tmp + rename）
          - 合并冲突：抛 FileConflictError，含 merged_content + conflict_markers + current_mtime

        返回 (saved_content, new_mtime)。saved_content 是实际写入磁盘的内容
        （直接保存时为 content，合并时为 merged_content）。

        已知 TOCTOU 限制：mtime 检测与写入之间无文件锁，极端并发下仍可能丢更新
        （A 读 mtime=T1 → B 写入 T2 → A 覆盖 T1）。MVP 单实例低并发可接受；
        SaaS 阶段需引入按文件锁或 DB 串行化。
        """
        repo_root = self._repo_path(project_id, repo_name)
        full = self._validate_path(repo_root, file_path)
        full.parent.mkdir(parents=True, exist_ok=True)

        # 无 expected_mtime：直接覆盖
        if expected_mtime is None:
            self._atomic_write(full, content)
            return content, os.path.getmtime(full)

        # 文件不存在：视作新文件，直接保存
        if not full.exists():
            self._atomic_write(full, content)
            return content, os.path.getmtime(full)

        current_mtime = os.path.getmtime(full)
        # mtime 一致：无并发修改，直接保存
        # Why rel_tol=0 + abs_tol=1μs：math.isclose 默认 rel_tol=1e-9，对 ~1.78e9 的时间戳
        # 相对容差 ≈ 1.78s，会把 1s 内的并发修改误判为"一致"。禁用相对容差，仅用绝对容差。
        if math.isclose(current_mtime, expected_mtime, rel_tol=0, abs_tol=1e-6):
            self._atomic_write(full, content)
            return content, os.path.getmtime(full)

        # mtime 不一致：三方合并
        # original_content 必填（已在前端/路由校验，此处防御性断言）
        if original_content is None:
            # 缺 original_content 无法合并，退化为直接保存（避免数据丢失）
            logger.warning("expected_mtime 提供但 original_content 缺失，退化为直接保存: %s", file_path)
            self._atomic_write(full, content)
            return content, os.path.getmtime(full)

        try:
            theirs = full.read_text(encoding="utf-8")
        except UnicodeDecodeError as e:
            # 二进制文件无法做文本三方合并——退化为直接覆盖
            # Why：FileService 是文本编辑场景，二进制文件不应走 merge 路径；
            # 真正的二进制冲突解决应走专属工具（如 LFS lock），不在本层处理
            logger.warning("文件 %s 非文本（%s），跳过三方合并直接覆盖", file_path, e)
            self._atomic_write(full, content)
            return content, os.path.getmtime(full)

        merge_result = self._git.merge_file(mine=content, original=original_content, theirs=theirs)

        if merge_result.success:
            self._atomic_write(full, merge_result.merged_content)
            return merge_result.merged_content, os.path.getmtime(full)

        # 合并冲突：抛 FileConflictError 让路由返回 409
        raise FileConflictError(
            path=file_path,
            merged_content=merge_result.merged_content,
            conflict_markers=merge_result.conflict_markers,
            current_mtime=current_mtime,
        )

    def _atomic_write(self, full: Path, content: str) -> None:
        """原子写入：写临时文件 + rename，避免读到半写状态"""
        fd, tmp_path = tempfile.mkstemp(dir=str(full.parent), prefix="." + full.name + ".", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
            os.replace(tmp_path, str(full))
        except Exception:
            Path(tmp_path).unlink(missing_ok=True)
            raise


class FileConflictError(Exception):
    """三方合并冲突——路由层翻译为 409 响应"""

    def __init__(
        self,
        path: str,
        merged_content: str,
        conflict_markers: list[str],
        current_mtime: float,
    ) -> None:
        super().__init__(f"文件保存冲突: {path}")
        self.path = path
        self.merged_content = merged_content
        self.conflict_markers = conflict_markers
        self.current_mtime = current_mtime
