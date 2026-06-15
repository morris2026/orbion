"""Git集成与审批后自动commit"""

import asyncio
import logging
import os
from pathlib import Path

import git

from app.config import Settings
from app.hub.events.bus import EventBus
from app.hub.events.projections import EventProjectionsProtocol
from app.hub.events.types import Event, EventType

logger = logging.getLogger(__name__)


def _sanitize_file_path(fp: str) -> str | None:
    """清洗文件路径：拒绝路径遍历（..）和绝对路径，返回安全的相对路径或None"""
    if ".." in fp.split(os.sep) or ".." in fp.split("/") or fp.startswith("/") or fp.startswith("\\"):
        return None
    cleaned = fp.lstrip("/").lstrip("\\")
    return cleaned


class GitService:
    """产出审批通过后自动commit到本地git仓库

    EventBus订阅者：订阅TaskOutputApproved事件，
    收到事件后从projections查询产出详情，写入文件并commit。
    仓库按项目隔离：projects/<id>/repo/<name>/
    """

    def __init__(
        self,
        settings: Settings,
        event_bus: EventBus,
        projections: EventProjectionsProtocol,
    ) -> None:
        self._settings = settings
        self._event_bus = event_bus
        self._projections = projections
        self._event_bus.subscribe(EventType.TaskOutputApproved, self._on_output_approved)

    def _resolve_repo_path(self, project_id: str, repo_name: str) -> str:
        return str(self._settings.project_repo_path(project_id, repo_name).resolve())

    async def ensure_repo(self, project_id: str, repo_name: str = "orbion") -> None:
        """确保项目仓库存在且已初始化（git init + 初始commit）"""
        repo_path = self._resolve_repo_path(project_id, repo_name)
        if not os.path.exists(repo_path):
            os.makedirs(repo_path, exist_ok=True)

        try:
            git.Repo(repo_path)
        except git.InvalidGitRepositoryError:
            repo = git.Repo.init(repo_path)
            readme = Path(repo_path) / "README.md"
            readme.write_text("# Orbion Project\n")
            repo.index.add(["README.md"])
            repo.index.commit("init: Orbion project repo")

    async def _on_output_approved(self, event: Event) -> None:
        """TaskOutputApproved事件处理器：写入产出文件并commit"""
        project_id = event.project_id
        if not project_id:
            logger.warning("TaskOutputApproved事件缺少project_id，跳过git commit")
            return

        output_id = event.payload.get("output_id", "")
        if not output_id:
            logger.warning("TaskOutputApproved事件缺少output_id，跳过git commit")
            return

        output = await self._projections.get_output_by_id(output_id)
        if output is None:
            logger.warning("产出%s在投影中不存在，跳过git commit", output_id)
            return

        repo_name = "orbion"
        await self.ensure_repo(project_id, repo_name)
        repo_path = self._resolve_repo_path(project_id, repo_name)

        file_paths: list[str] = output.get("file_paths", [])
        content: str = output.get("content", "")

        safe_paths: list[str] = []
        for fp in file_paths:
            safe = _sanitize_file_path(fp)
            if safe is None:
                logger.warning("产出%s的file_path '%s'包含路径遍历或绝对路径，跳过此文件", output_id, fp)
                continue
            safe_paths.append(safe)
            full_path = Path(repo_path) / safe
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content)

        if not safe_paths:
            logger.warning("产出%s无有效file_paths，跳过git commit", output_id)
            return

        await asyncio.to_thread(self._commit_files, repo_path, safe_paths, output_id)

    def _commit_files(self, repo_path: str, safe_paths: list[str], output_id: str) -> None:
        """同步执行git add + commit（由asyncio.to_thread调度）"""
        repo = git.Repo(repo_path)
        repo.index.add(safe_paths)
        repo.index.commit(f"[approve] output {output_id}")

    def get_recent_commits(self, project_id: str, repo_name: str = "orbion", limit: int = 10) -> list[dict[str, str]]:
        """查询项目仓库的git log返回最近N条commit摘要"""
        repo_path = self._resolve_repo_path(project_id, repo_name)
        if not Path(repo_path).exists():
            return []
        repo = git.Repo(repo_path)
        commits = list(repo.iter_commits(max_count=limit))
        return [{"message": str(c.message), "hexsha": str(c.hexsha)} for c in commits]

    def _staged_status_code(self, item: object) -> str:
        """从 index.diff('HEAD') 的 item 推断 staged 状态码

        Why: index.diff('HEAD') 方向是 HEAD→index，语义与直觉相反：
        deleted_file=True 实际是新增（HEAD 中不存在），new_file=True 实际是删除
        """
        if getattr(item, "deleted_file", False):
            return "A"
        if getattr(item, "new_file", False):
            return "D"
        if getattr(item, "renamed_file", False):
            return "R"
        return "M"

    def _changes_status_code(self, item: object) -> str:
        """从 index.diff(None) 的 item 推断 changes 状态码"""
        if getattr(item, "new_file", False):
            return "A"
        if getattr(item, "deleted_file", False):
            return "D"
        if getattr(item, "renamed_file", False):
            return "R"
        return "M"

    def _validate_paths(self, paths: list[str]) -> None:
        """校验文件路径列表：拒绝路径穿越和绝对路径"""
        for p in paths:
            if _sanitize_file_path(p) is None:
                raise ValueError(f"无效的文件路径: {p}")

    def status(self, project_id: str, repo_name: str) -> dict[str, list[dict[str, str]]]:
        """git status 返回 staged/changes 分组文件列表"""
        repo_path = self._resolve_repo_path(project_id, repo_name)
        if not Path(repo_path).exists():
            raise FileNotFoundError(f"仓库不存在: {repo_name}")
        repo = git.Repo(repo_path)
        staged: list[dict[str, str]] = []
        changes: list[dict[str, str]] = []
        try:
            for item in repo.index.diff("HEAD", create_patch=False):
                path = item.a_path or ""
                staged.append({"path": path, "status": self._staged_status_code(item)})
        except git.exc.BadName:
            for entry in repo.index.entries:
                if isinstance(entry, tuple):
                    staged.append({"path": str(entry[0]), "status": "A"})
        for item in repo.index.diff(None, create_patch=False):
            path = item.a_path or ""
            changes.append({"path": path, "status": self._changes_status_code(item)})
        for uf in repo.untracked_files:
            changes.append({"path": str(uf), "status": "U"})
        return {"staged": staged, "changes": changes}

    def stage(self, project_id: str, repo_name: str, paths: list[str]) -> None:
        """git add 指定文件"""
        repo_path = self._resolve_repo_path(project_id, repo_name)
        if not Path(repo_path).exists():
            raise FileNotFoundError(f"仓库不存在: {repo_name}")
        self._validate_paths(paths)
        repo = git.Repo(repo_path)
        repo.index.add(paths)

    def unstage(self, project_id: str, repo_name: str, paths: list[str]) -> None:
        """git reset HEAD 指定文件（无 commit 时从 index 移除，文件变为 untracked）"""
        repo_path = self._resolve_repo_path(project_id, repo_name)
        if not Path(repo_path).exists():
            raise FileNotFoundError(f"仓库不存在: {repo_name}")
        self._validate_paths(paths)
        repo = git.Repo(repo_path)
        if repo.head.is_valid():
            for p in paths:
                repo.index.reset(p, head=True)
        else:
            repo.index.remove(paths, working_tree=False)

    def commit(self, project_id: str, repo_name: str, message: str) -> str:
        """git commit 已 staged 的文件，返回 commit hexsha"""
        repo_path = self._resolve_repo_path(project_id, repo_name)
        if not Path(repo_path).exists():
            raise FileNotFoundError(f"仓库不存在: {repo_name}")
        repo = git.Repo(repo_path)
        try:
            has_staged = bool(repo.index.diff("HEAD", create_patch=False))
        except git.exc.BadName:
            has_staged = bool(repo.index.entries)
        if not has_staged:
            raise ValueError("无可提交的变更")
        commit_obj = repo.index.commit(message)
        return str(commit_obj.hexsha)
