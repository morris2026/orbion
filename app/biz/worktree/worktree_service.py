"""WorktreeService — worktree 生命周期核心管理

设计文档：docs/specs/1.10-mvp-git-worktree-model.md §6.4

实现 step 2 范围：create_or_reuse / archive / get / list_by_project。
实现 step 4 范围：merge / regenerate。
实现 step 5 范围：delete_by_owner。
全局 git 锁（§5.4）串行化所有 git 操作。worktrees 表 status 三态流转
（active / conflicting / archived）。

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
from app.biz.git.git_service import GitCommandService, MergeResult
from app.biz.worktree.models import TaskContext, TaskResolver, Worktree
from app.config import Settings

logger = logging.getLogger(__name__)

_BASE_BRANCH = "main"
# repo_name 路径安全校验：防 TaskResolver 实现从外部输入引入路径遍历
_REPO_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_.\-]+$")


class WorktreeService:
    """worktree 生命周期管理（create_or_reuse / archive / merge / regenerate / get / list_by_project）

    依赖：
    - GitCommandService：git 命令封装（worktree add/remove、branch create/delete、merge）
    - Settings：定位 bare 仓库路径
    - asyncpg.Pool：worktrees 表读写
    - TaskResolver：task_id → TaskContext（project_id / repo_name / owner_user_id）
    - max_conflict_regenerations：合并冲突重生成次数上限（§8.1，默认 3）
    """

    def __init__(
        self,
        git: GitCommandService,
        settings: Settings,
        pool: asyncpg.Pool,
        task_resolver: TaskResolver,
        max_conflict_regenerations: int = 3,
    ) -> None:
        self._git = git
        self._settings = settings
        self._pool = pool
        self._task_resolver = task_resolver
        self._max_conflict_regenerations = max_conflict_regenerations

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

    async def merge(self, task_id: uuid.UUID, target_branch: str = _BASE_BRANCH) -> MergeResult:
        """合并 task worktree 到目标分支（设计 §6.4、§8）

        - 加全局 git 锁
        - git merge task/{task_id} 到 target worktree（main）
        - 成功：archive task worktree
        - 冲突：调 regenerate() 自动重生成
        返回 MergeResult（success / has_conflicts / conflict_files）。
        异常：
          - WorktreeConflictError（冲突且重生成次数超限）
          - GitOperationError（merge 内部异常）
        """
        wt = await self._fetch_active_by_task(task_id)
        if wt is None:
            raise WorktreeNotFoundError(f"task {task_id} 无 active worktree，无法 merge")

        # MVP 仅支持合并到 main worktree；target_branch 参数为未来扩展预留
        if target_branch != _BASE_BRANCH:
            raise ValueError(f"MVP 仅支持 target_branch='main'，收到 '{target_branch}'")

        ctx = await self._resolve_task(task_id)
        self._validate_repo_name(ctx.repo_name)
        target_wt_path = self._main_worktree_path(ctx.project_id, ctx.repo_name)

        async with get_global_git_lock():
            # double-check：并发 merge 同一 task 时，持锁后再次确认 wt 仍 active
            # 防止 A 完成 archive 后 B 拿到已删除的 branch 报 GitOperationError
            current = await self._fetch_active_by_task(task_id)
            if current is None or current.id != wt.id:
                raise WorktreeNotFoundError(f"task {task_id} worktree 已被并发修改，放弃 merge")

            result = await asyncio.to_thread(self._git.merge, str(target_wt_path), wt.branch_name)

            if result.success:
                # 合并成功：archive task worktree（main 已含 task commits）
                await self._archive_inside_lock(wt, task_id)
                return result

            # 冲突：merge 已自动 abort，main 回到合并前状态
            if result.has_conflicts:
                logger.info("task %s merge 冲突，触发 regenerate", task_id)
                await self._regenerate_inside_lock(wt, task_id, ctx)
                return result

            # 非 0 退出且无冲突标记：其他 git 错误
            raise GitOperationError(f"git merge 失败 (task={task_id}): {result.error}")

    async def regenerate(self, task_id: uuid.UUID) -> Worktree:
        """冲突重生成：删除当前 worktree + 分支，基于最新 main 重建（设计 §6.4、§8.1）

        - conflict_regen_count 递增
        - 超过 MAX_CONFLICT_REGENERATIONS 抛 WorktreeConflictError
        - archive 当前 worktree → create_or_reuse 基于最新 main 重建
        返回新 Worktree。
        异常：
          - WorktreeConflictError（冲突重生成次数超限）
          - WorktreeNotFoundError（task 无 active worktree）
        """
        wt = await self._fetch_active_by_task(task_id)
        if wt is None:
            raise WorktreeNotFoundError(f"task {task_id} 无 active worktree，无法 regenerate")

        ctx = await self._resolve_task(task_id)
        self._validate_repo_name(ctx.repo_name)
        async with get_global_git_lock():
            return await self._regenerate_inside_lock(wt, task_id, ctx)

    async def _regenerate_inside_lock(self, wt: Worktree, task_id: uuid.UUID, ctx: TaskContext) -> Worktree:
        """锁内执行重生成：检查超限 → archive → create_or_use + 递增计数"""
        # 检查超限（含当前这次）
        new_count = wt.conflict_regen_count + 1
        if new_count > self._max_conflict_regenerations:
            logger.warning(
                "task %s 冲突重生成超限（%d > %d），清理 worktree 后抛 WorktreeConflictError",
                task_id,
                new_count,
                self._max_conflict_regenerations,
            )
            # 超限也清理旧 worktree，让重新 dispatch 走"首次创建"分支基于最新 main
            await self._archive_inside_lock(wt, task_id)
            raise WorktreeConflictError(
                f"task {task_id} 冲突重生成次数超限（{new_count} > MAX {self._max_conflict_regenerations}），"
                f"已清理旧 worktree，请重新 dispatch 或取消 task"
            )

        # 标记 conflicting（短暂，用于通知用户）
        await self._pool.execute(
            "UPDATE worktrees SET status = 'conflicting', updated_at = NOW() WHERE id = $1",
            wt.id,
        )

        # archive 当前 worktree（含冲突产出）
        await self._archive_inside_lock(wt, task_id)

        # create_or_reuse 基于最新 main 重建（复用已有锁，不重新获取）
        # 若创建失败，旧 worktree 已 archived 无法恢复——抛异常让调用方处理
        # （merge/regenerate 的调用方应记录此状态，人工介入或重试 dispatch）
        try:
            new_wt = await self._create_worktree_for_task(task_id, ctx)
        except WorktreeCreateError:
            logger.error(
                "task %s regenerate 创建新 worktree 失败（旧已 archived），需人工介入",
                task_id,
                exc_info=True,
            )
            raise

        # 新 worktree 继承递增后的计数
        await self._pool.execute(
            "UPDATE worktrees SET conflict_regen_count = $1, updated_at = NOW() WHERE id = $2",
            new_count,
            new_wt.id,
        )
        new_wt.conflict_regen_count = new_count
        logger.info("task %s regenerated: worktree %s → %s (count=%d)", task_id, wt.id, new_wt.id, new_count)
        return new_wt

    async def _archive_inside_lock(self, wt: Worktree, task_id: uuid.UUID) -> None:
        """锁内执行 archive（不重新获取锁），复用 archive 逻辑但跳过锁/状态检查"""
        bare_repo = self._bare_repo_path(wt.project_id, wt.repo_name)
        rm_result = await asyncio.to_thread(self._git.worktree_remove, str(bare_repo), wt.path, True)
        if not rm_result.success:
            raise WorktreeArchiveError(f"git worktree remove 失败 (task={task_id}): {rm_result.error}")
        del_result = await asyncio.to_thread(self._git.branch_delete, str(bare_repo), wt.branch_name, True)
        if not del_result.success:
            raise WorktreeArchiveError(f"git branch delete 失败 (task={task_id}): {del_result.error}")
        await self._pool.execute("UPDATE worktrees SET status = 'archived', updated_at = NOW() WHERE id = $1", wt.id)

    async def _create_worktree_for_task(self, task_id: uuid.UUID, ctx: TaskContext) -> Worktree:
        """锁内创建新 task worktree（复用 create_or_reuse 逻辑但不重新获取锁）

        DB INSERT 失败时回滚 git 操作避免孤儿 worktree（与 create_or_reuse 对称）。
        """
        bare_repo = self._bare_repo_path(ctx.project_id, ctx.repo_name)
        worktree_path = self._task_worktree_path(ctx.project_id, ctx.repo_name, task_id)
        branch_name = f"task/{task_id}"

        result = await asyncio.to_thread(
            self._git.worktree_add,
            str(bare_repo),
            str(worktree_path),
            branch_name,
            _BASE_BRANCH,
        )
        if not result.success:
            raise WorktreeCreateError(f"git worktree add 失败 (task={task_id}): {result.error}")

        try:
            return await self._insert_task_worktree(
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

    async def delete_by_owner(self, worktree_id: uuid.UUID, user_id: uuid.UUID) -> None:
        """task 执行者主动放弃（设计 §6.4、§10.3）

        AgentRuntime.cancel(task_id) 的 worktree 层入口——AgentRuntime.cancel 负责
        task 状态流转（→cancelled）+ artifact 处理（→rejected），内部调用本方法完成
        worktree archive。本方法只负责 worktree 层操作。

        - 校验 worktree 存在
        - 校验 worktree_type='task'（main 不可删）
        - 校验 user_id 是 worktree owner（created_by）
        - 校验 task 状态为 pending/running/paused/timeout（completed/cancelled 不允许）
        - 调用 archive() 清理 worktree

        异常：
          - WorktreeNotFoundError（worktree_id 不存在）
          - PermissionError（非 owner 或 main worktree）
          - TaskStateError（task 状态不允许放弃）
        """
        wt = await self.get(worktree_id)
        if wt is None:
            raise WorktreeNotFoundError(f"worktree {worktree_id} 不存在")

        # main worktree 不可删
        if wt.worktree_type == "main":
            raise PermissionError(f"main worktree {worktree_id} 不可删除")

        # owner 校验
        if wt.created_by != user_id:
            raise PermissionError(f"user {user_id} 不是 worktree {worktree_id} 的 owner（owner={wt.created_by}）")

        # task 状态校验
        if wt.task_id is None:
            # task 类型 worktree 必有 task_id；None 表示数据完整性问题
            logger.warning("worktree %s 类型为 task 但 task_id 为 None，数据异常", worktree_id)
        else:
            ctx = await self._resolve_task(wt.task_id)
            forbidden = {"completed", "cancelled"}
            if ctx.task_status in forbidden:
                raise TaskStateError(
                    f"task {wt.task_id} 状态为 {ctx.task_status}，不允许放弃（仅 pending/running/paused/timeout 允许）"
                )

        # archive 清理 worktree（task_id 非空才 archive，None 时无 task 关联无文件可删）
        if wt.task_id is not None:
            await self.archive(wt.task_id)

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

    def _main_worktree_path(self, project_id: uuid.UUID, repo_name: str) -> Path:
        """main worktree 路径：projects/{project_id}/repo/worktrees/main/（设计 §2 merge 目标）"""
        return self._settings.project_dir(str(project_id)) / "repo" / "worktrees" / "main"

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


class WorktreeConflictError(RuntimeError):
    """合并冲突且重生成次数超限（§8.1）"""


class WorktreeNotFoundError(RuntimeError):
    """task 无 active worktree（merge/regenerate 时查不到）"""


class GitOperationError(RuntimeError):
    """git 命令执行异常（merge 内部错误等）"""


class TaskStateError(RuntimeError):
    """task 状态不允许此操作（如 completed/cancelled 不允许 delete_by_owner）"""


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
        conflict_regen_count=row["conflict_regen_count"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
