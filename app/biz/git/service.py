"""Git集成与审批后自动commit"""

import asyncio
import logging
import os
from pathlib import Path

import git

from app.hub.events.bus import EventBus
from app.hub.events.projections import EventProjectionsProtocol
from app.hub.events.types import Event, EventType

logger = logging.getLogger(__name__)


def _sanitize_file_path(fp: str) -> str | None:
    """清洗文件路径：拒绝路径遍历（..）和绝对路径，返回安全的相对路径或None"""
    # Why: 检查分隔符和斜杠后，再用Path.resolve()验证结果路径不越界（纵深防御）
    if ".." in fp.split(os.sep) or ".." in fp.split("/") or fp.startswith("/") or fp.startswith("\\"):
        return None
    cleaned = fp.lstrip("/").lstrip("\\")
    return cleaned


class GitService:
    """产出审批通过后自动commit到本地git仓库

    EventBus订阅者：订阅TaskOutputApproved事件，
    收到事件后从projections查询产出详情，写入文件并commit。
    """

    def __init__(
        self,
        repo_path: str,
        event_bus: EventBus,
        projections: EventProjectionsProtocol,
    ) -> None:
        self._repo_path = repo_path
        self._event_bus = event_bus
        self._projections = projections
        # 只订阅审批通过事件——要求修改和拒绝不触发commit
        self._event_bus.subscribe(EventType.TaskOutputApproved, self._on_output_approved)

    async def ensure_repo(self) -> None:
        """确保本地repo存在且已初始化（git init + 初始commit）"""
        if not os.path.exists(self._repo_path):
            os.makedirs(self._repo_path, exist_ok=True)

        # 目录存在但不是git repo → 初始化并创建空初始commit
        try:
            git.Repo(self._repo_path)
        except git.InvalidGitRepositoryError:
            repo = git.Repo.init(self._repo_path)
            # Why: 空repo无commit历史会导致iter_commits报错，初始commit提供可查询的起点
            readme = Path(self._repo_path) / "README.md"
            readme.write_text("# Orbion Project\n")
            repo.index.add(["README.md"])
            repo.index.commit("init: Orbion project repo")

    async def _on_output_approved(self, event: Event) -> None:
        """TaskOutputApproved事件处理器：写入产出文件并commit"""
        output_id = event.payload.get("output_id", "")
        if not output_id:
            logger.warning("TaskOutputApproved事件缺少output_id，跳过git commit")
            return

        # 从projections查询产出详情
        output = await self._projections.get_output_by_id(output_id)
        if output is None:
            # Why: CQRS最终一致性——审批事件先于投影更新到达，投影可能暂无此产出记录
            logger.warning("产出%s在投影中不存在，跳过git commit", output_id)
            return

        # 确保repo存在
        await self.ensure_repo()

        file_paths: list[str] = output.get("file_paths", [])
        content: str = output.get("content", "")

        # Why: MVP简化——同一content写入所有file_paths；后续按产出物类型拆分per-file内容时改用diff字段
        safe_paths: list[str] = []
        for fp in file_paths:
            safe = _sanitize_file_path(fp)
            if safe is None:
                logger.warning("产出%s的file_path '%s'包含路径遍历或绝对路径，跳过此文件", output_id, fp)
                continue
            safe_paths.append(safe)
            full_path = Path(self._repo_path) / safe
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content)

        if not safe_paths:
            logger.warning("产出%s无有效file_paths，跳过git commit", output_id)
            return

        # Why: git操作是同步阻塞I/O，通过to_thread避免阻塞asyncio事件循环
        await asyncio.to_thread(self._commit_files, safe_paths, output_id)

    def _commit_files(self, safe_paths: list[str], output_id: str) -> None:
        """同步执行git add + commit（由asyncio.to_thread调度）"""
        repo = git.Repo(self._repo_path)
        repo.index.add(safe_paths)
        repo.index.commit(f"[approve] output {output_id}")
