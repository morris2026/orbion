"""WorktreeService 跨项目并发测试 — GW-2.7

验证全局 git 锁串行化但不死锁。同项目 4 个并发 create_or_reuse 共享同一 bare 仓库的
.git/ 目录，无锁会触发 .git/index.lock 冲突；有锁则串行通过。
"""

from __future__ import annotations

import asyncio
import subprocess
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import cast

import asyncpg
import pytest

from app.biz.git.git_service import GitCommandService
from app.biz.worktree.worktree_service import WorktreeService
from app.config import Settings

from ._worktree_helpers import StubTaskResolver, init_bare_repo


@pytest.fixture
async def db_pool() -> AsyncGenerator[asyncpg.Pool, None]:
    from app.config import get_settings

    pool = await asyncpg.create_pool(get_settings().postgres.url, min_size=2, max_size=10)
    yield pool
    await pool.close()


@pytest.fixture
async def worktree_service(db_pool: asyncpg.Pool, tmp_path: Path) -> AsyncGenerator[WorktreeService, None]:
    settings = Settings(jwt_secret="test-secret-32bytes-for-jwt-hs256", root_dir=str(tmp_path))
    resolver = StubTaskResolver()
    svc = WorktreeService(GitCommandService(), settings, db_pool, resolver)
    yield svc


async def _setup_project_with_tasks(
    db_pool: asyncpg.Pool, resolver: StubTaskResolver, tmp_path: Path, label: str, n: int
) -> tuple[list[uuid.UUID], Path]:
    """创建项目 + bare 仓库 + 注册 n 个 task，返回 (task_ids, bare_repo_path)"""
    project_id = uuid.uuid4()
    repo_name = "orbion"
    owner_user_id = uuid.uuid4()

    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO projects (id, name, description, tenant_id, default_thread_id, created_at) "
            "VALUES ($1, $2, $3, 'default', NULL, NOW())",
            project_id,
            f"gw27-{label}-{project_id.hex[:8]}",
            "test",
        )

    bare_repo = tmp_path / "projects" / str(project_id) / "repo" / f"{repo_name}.git"
    init_bare_repo(bare_repo)

    task_ids = [uuid.uuid4() for _ in range(n)]
    for tid in task_ids:
        resolver.register(tid, project_id, repo_name, owner_user_id)
    return task_ids, bare_repo


# GW-2.7 同项目并发 git 锁串行化但不死锁
async def test_same_project_concurrent_no_deadlock(
    worktree_service: WorktreeService,
    db_pool: asyncpg.Pool,
    tmp_path: Path,
) -> None:
    """同项目 4 个并发 create_or_reuse 共享同一 bare 仓库 .git/ 目录

    检查项：
    - 4 个任务全部成功完成（无死锁）
    - 无 .git/index.lock 冲突错误（全局锁串行化的直接证据——若无锁，并发 git
      worktree add 会因 .git/worktrees/ 元数据竞争报 fatal 错误）
    - 每个任务的 worktree + branch 都创建成功
    """
    resolver = cast(StubTaskResolver, worktree_service.task_resolver)

    # 同一项目注册 4 个 task（共享 bare 仓库）
    task_ids, bare_repo = await _setup_project_with_tasks(db_pool, resolver, tmp_path, "p1", 4)

    # 4 个并发 create_or_reuse
    results = await asyncio.gather(
        *(worktree_service.create_or_reuse(tid) for tid in task_ids),
        return_exceptions=True,
    )

    # 全部成功（无异常）—— 若全局锁失效，部分会因 .git/index.lock 失败
    for r in results:
        assert not isinstance(r, BaseException), f"并发任务失败: {r}"
        assert r.status == "active"

    # 每个任务的 worktree + branch 都创建成功
    for tid in task_ids:
        wt_path = bare_repo.parent / "worktrees" / f"task_{tid}"
        assert wt_path.is_dir(), f"worktree 目录未创建: {wt_path}"
        branches = subprocess.run(
            ["git", "-C", str(bare_repo), "branch", "--list"], capture_output=True, text=True, check=True
        ).stdout
        assert f"task/{tid}" in branches, f"branch 未创建: task/{tid}"

    # worktrees 表共 4 条 active 记录
    async with db_pool.acquire() as conn:
        active_count = await conn.fetchval("SELECT COUNT(*) FROM worktrees WHERE status = 'active'")
    assert active_count >= 4


# GW-2.7 跨项目并发也通过同一全局锁串行化
async def test_cross_project_concurrent_no_deadlock(
    worktree_service: WorktreeService,
    db_pool: asyncpg.Pool,
    tmp_path: Path,
) -> None:
    """2 个项目各 2 个并发 create_or_reuse 共 4 个任务

    检查项：4 个任务全部成功；跨项目共享全局锁不死锁。
    """
    resolver = cast(StubTaskResolver, worktree_service.task_resolver)

    p1_tasks, p1_bare = await _setup_project_with_tasks(db_pool, resolver, tmp_path, "p1", 2)
    p2_tasks, p2_bare = await _setup_project_with_tasks(db_pool, resolver, tmp_path, "p2", 2)

    results = await asyncio.gather(
        *(worktree_service.create_or_reuse(tid) for tid in p1_tasks + p2_tasks),
        return_exceptions=True,
    )

    for r in results:
        assert not isinstance(r, BaseException), f"跨项目并发任务失败: {r}"
        assert r.status == "active"

    for tid, bare in [(p1_tasks[0], p1_bare), (p1_tasks[1], p1_bare), (p2_tasks[0], p2_bare), (p2_tasks[1], p2_bare)]:
        wt_path = bare.parent / "worktrees" / f"task_{tid}"
        assert wt_path.is_dir()
