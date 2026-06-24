"""WorktreeService — worktree 生命周期核心管理

设计文档：docs/specs/1.10-mvp-git-worktree-model.md §6.4

实现 step 2 范围：create_or_reuse / archive / get / list_by_project。
全局 git 锁（§5.4）串行化所有 git 操作。worktrees 表 status 三态流转
（active / conflicting / archived）。

merge / regenerate / delete_by_owner 在后续步骤实现。
事件发布（WorktreeCreated 等）在 step 6 实现，本步骤不发布事件。
"""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from pathlib import Path

import asyncpg

from app.biz.git.git_lock import get_global_git_lock
from app.biz.git.git_service import GitCommandService
from app.biz.worktree.models import TaskContext, TaskResolver, Worktree
from app.config import Settings

logger = logging.getLogger(__name__)

_BASE_BRANCH = "main"
# repo_name 路径安全校验：防 TaskResolver 实现从外部输入引入路径遍历
_REPO_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_.\-]+$")


class WorktreeService:
    """worktree 生命周期管理（create_or_reuse / archive / get / list_by_project）

    依赖：
    - GitCommandService：git 命令封装（worktree add/remove、branch create/delete）
    - Settings：定位 bare 仓库路径
    - asyncpg.Pool：worktrees 表读写
    - TaskResolver：task_id → TaskContext（project_id / repo_name / owner_user_id）
    """

    def __init__(
        self,
        git: GitCommandService,
        settings: Settings,
        pool: asyncpg.Pool,
        task_resolver: TaskResolver,
    ) -> None:
        self._git = git
        self._settings = settings
        self._pool = pool
        self._task_resolver = task_resolver

    # -- 只读访问（供测试/上层诊断） ------------------------------------

    @property
    def pool(self) -> asyncpg.Pool:
        """worktrees 表连接池（只读暴露）"""
        return self._pool

    @property
    def task_resolver(self) -> TaskResolver:
        """TaskResolver 实例（只读暴露）"""
        return self._task_resolver

    # -- 生命周期方法 -----------------------------------------------------

    async def create_or_reuse(self, task_id: uuid.UUID) -> Worktree:
        """为 task 创建或复用 worktree（设计 §6.4）

        - 首次 dispatch：查无 active worktree → 加全局锁 → git worktree add + insert
        - revision 重做：查有 active worktree → 直接返回，保留之前产出

        异常：
        - TaskNotFoundError：task_id 在 TaskResolver 中未注册
        - WorktreeCreateError：git worktree add 失败或 DB INSERT 失败（含回滚后仍失败）
        """
        # 1. 查是否已有 active worktree（不加锁，快速路径）
        existing = await self._fetch_active_by_task(task_id)
        if existing is not None:
            logger.info("task %s 复用 worktree %s", task_id, existing.id)
            return existing

        # 2. 首次创建：解析 task 上下文 + 加全局锁串行化 git 操作
        ctx = await self._resolve_task(task_id)
        self._validate_repo_name(ctx.repo_name)
        async with get_global_git_lock():
            # double-check：并发 dispatch 同一 task 时，持锁后再次确认
            existing_after_lock = await self._fetch_active_by_task(task_id)
            if existing_after_lock is not None:
                return existing_after_lock

            bare_repo = self._bare_repo_path(ctx.project_id, ctx.repo_name)
            worktree_path = self._task_worktree_path(ctx.project_id, ctx.repo_name, task_id)
            branch_name = f"task/{task_id}"

            # git 操作通过 to_thread 调度，避免 subprocess 阻塞 event loop
            result = await asyncio.to_thread(
                self._git.worktree_add,
                str(bare_repo),
                str(worktree_path),
                branch_name,
                _BASE_BRANCH,
            )
            if not result.success:
                raise WorktreeCreateError(f"git worktree add 失败 (task={task_id}): {result.error}")

            # DB INSERT；失败时回滚 git 操作避免孤儿 worktree
            try:
                wt = await self._insert_task_worktree(
                    task_id=task_id,
                    project_id=ctx.project_id,
                    repo_name=ctx.repo_name,
                    branch_name=branch_name,
                    path=str(worktree_path),
                    created_by=ctx.owner_user_id,
                )
            except asyncpg.PostgresError as e:
                logger.error("DB INSERT worktree 失败，回滚 git 操作: %s", e)
                rm = await asyncio.to_thread(self._git.worktree_remove, str(bare_repo), str(worktree_path), True)
                if not rm.success:
                    logger.warning("回滚 worktree_remove 失败，可能残留孤儿: %s", rm.error)
                del_r = await asyncio.to_thread(self._git.branch_delete, str(bare_repo), branch_name, True)
                if not del_r.success:
                    logger.warning("回滚 branch_delete 失败，可能残留分支: %s", del_r.error)
                raise WorktreeCreateError(f"DB INSERT 失败 (task={task_id}): {e}") from e

            logger.info("task %s 创建 worktree %s at %s", task_id, wt.id, worktree_path)
            return wt

    async def archive(self, task_id: uuid.UUID) -> None:
        """归档 task worktree（设计 §6.4）

        - worktree 存在：加全局锁 → worktree remove + branch delete + status='archived'
        - worktree 不存在（pending 首次）：no-op，不抛错

        异常：
        - WorktreeArchiveError：git worktree remove 或 branch delete 失败
        """
        wt = await self._fetch_active_by_task(task_id)
        if wt is None:
            logger.info("task %s 无 active worktree，archive 为 no-op", task_id)
            return

        self._validate_repo_name(wt.repo_name)
        async with get_global_git_lock():
            # double-check：并发 archive 同一 task 时，持锁后再次确认状态
            # _fetch_active_by_task 已 WHERE status != 'archived'，archived 时返回 None
            current = await self._fetch_active_by_task(task_id)
            if current is None:
                logger.info("task %s worktree 已被并发 archive，跳过", task_id)
                return

            bare_repo = self._bare_repo_path(wt.project_id, wt.repo_name)
            # worktree remove（force=True，归档场景产出已合并或显式丢弃）
            rm_result = await asyncio.to_thread(self._git.worktree_remove, str(bare_repo), wt.path, True)
            if not rm_result.success:
                raise WorktreeArchiveError(f"git worktree remove 失败 (task={task_id}): {rm_result.error}")
            # branch delete（force=True，archive 契约）
            del_result = await asyncio.to_thread(self._git.branch_delete, str(bare_repo), wt.branch_name, True)
            if not del_result.success:
                raise WorktreeArchiveError(f"git branch delete 失败 (task={task_id}): {del_result.error}")
            # 表状态更新
            await self._pool.execute(
                "UPDATE worktrees SET status = 'archived', updated_at = NOW() WHERE id = $1",
                wt.id,
            )
            logger.info("task %s worktree %s archived", task_id, wt.id)

    async def get(self, worktree_id: uuid.UUID) -> Worktree | None:
        """按 id 查询 worktree"""
        row = await self._pool.fetchrow("SELECT * FROM worktrees WHERE id = $1", worktree_id)
        if row is None:
            return None
        return _row_to_worktree(row)

    async def list_by_project(self, project_id: uuid.UUID) -> list[Worktree]:
        """列出项目所有 worktree（main + task），按 created_at 倒序"""
        rows = await self._pool.fetch(
            "SELECT * FROM worktrees WHERE project_id = $1 ORDER BY created_at DESC",
            project_id,
        )
        return [_row_to_worktree(r) for r in rows]

    # -- 内部辅助 ---------------------------------------------------------

    def _bare_repo_path(self, project_id: uuid.UUID, repo_name: str) -> Path:
        """bare 仓库路径：projects/{project_id}/repo/{repo_name}.git（设计 §2）"""
        return self._settings.project_dir(str(project_id)) / "repo" / f"{repo_name}.git"

    def _task_worktree_path(self, project_id: uuid.UUID, repo_name: str, task_id: uuid.UUID) -> Path:
        """task worktree 路径：projects/{project_id}/repo/worktrees/task_{task_id}/（设计 §2）"""
        return self._settings.project_dir(str(project_id)) / "repo" / "worktrees" / f"task_{task_id}"

    async def _fetch_active_by_task(self, task_id: uuid.UUID) -> Worktree | None:
        """查询 task 的非 archived worktree（active 或 conflicting）"""
        row = await self._pool.fetchrow(
            "SELECT * FROM worktrees WHERE task_id = $1 AND status != 'archived'",
            task_id,
        )
        if row is None:
            return None
        return _row_to_worktree(row)

    async def _resolve_task(self, task_id: uuid.UUID) -> TaskContext:
        """解析 task 上下文，翻译 KeyError 为 TaskNotFoundError"""
        try:
            return await self._task_resolver.resolve(task_id)
        except KeyError as e:
            raise TaskNotFoundError(f"task {task_id} 未在 TaskResolver 中注册") from e

    def _validate_repo_name(self, repo_name: str) -> None:
        """校验 repo_name 防路径遍历（TaskResolver 实现可能从外部输入）"""
        if not _REPO_NAME_PATTERN.match(repo_name):
            raise ValueError(f"无效的 repo_name: {repo_name}")

    async def _insert_task_worktree(
        self,
        task_id: uuid.UUID,
        project_id: uuid.UUID,
        repo_name: str,
        branch_name: str,
        path: str,
        created_by: uuid.UUID,
    ) -> Worktree:
        """插入 task worktree 记录并返回"""
        row = await self._pool.fetchrow(
            "INSERT INTO worktrees "
            "(project_id, repo_name, worktree_type, branch_name, path, status, created_by, task_id) "
            "VALUES ($1, $2, 'task', $3, $4, 'active', $5, $6) "
            "RETURNING *",
            project_id,
            repo_name,
            branch_name,
            path,
            created_by,
            task_id,
        )
        if row is None:
            raise RuntimeError("INSERT worktrees RETURNING 未返回行，DB 异常")
        return _row_to_worktree(row)


class WorktreeCreateError(RuntimeError):
    """git worktree add 失败或 DB INSERT 失败（含回滚后仍失败）"""


class WorktreeArchiveError(RuntimeError):
    """git worktree remove 或 branch delete 失败"""


class TaskNotFoundError(RuntimeError):
    """task_id 在 TaskResolver 中未注册"""


def _row_to_worktree(row: asyncpg.Record) -> Worktree:
    """asyncpg Record → Worktree dataclass"""
    return Worktree(
        id=row["id"],
        project_id=row["project_id"],
        repo_name=row["repo_name"],
        worktree_type=row["worktree_type"],
        branch_name=row["branch_name"],
        path=row["path"],
        status=row["status"],
        created_by=row["created_by"],
        task_id=row["task_id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
