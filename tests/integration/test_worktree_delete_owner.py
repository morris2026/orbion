"""WorktreeService delete_by_owner + 权限测试 — GW-5.1 ~ GW-5.6

使用真实 git 二进制 + tmp_path bare 仓库 + 真实 PostgreSQL worktrees 表，
验证 delete_by_owner 的 owner 校验、task 状态校验、main worktree 保护、archive 清理。
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from pathlib import Path

import asyncpg
import pytest

from app.biz.git.git_service import GitCommandService
from app.biz.worktree.worktree_service import TaskStateError, WorktreeService
from app.config import Settings

from ._worktree_helpers import StubTaskResolver, init_bare_repo


@pytest.fixture
async def db_pool() -> AsyncGenerator[asyncpg.Pool, None]:
    from app.config import get_settings

    pool = await asyncpg.create_pool(get_settings().postgres.url, min_size=1, max_size=5)
    yield pool
    await pool.close()


@pytest.fixture
async def worktree_service(
    db_pool: asyncpg.Pool, tmp_path: Path
) -> AsyncGenerator[tuple[WorktreeService, StubTaskResolver], None]:
    settings = Settings(jwt_secret="test-secret-32bytes-for-jwt-hs256", root_dir=str(tmp_path))
    resolver = StubTaskResolver()
    svc = WorktreeService(GitCommandService(), settings, db_pool, resolver)
    yield svc, resolver


async def _create_task_worktree(
    svc: WorktreeService,
    resolver: StubTaskResolver,
    tmp_path: Path,
    db_pool: asyncpg.Pool,
    task_status: str = "running",
) -> tuple[uuid.UUID, Path, uuid.UUID, uuid.UUID]:
    """创建项目 + bare 仓库 + 注册 task + 创建 task worktree

    返回 (task_id, bare_repo, owner_user_id, worktree_id)
    """
    project_id = uuid.uuid4()
    repo_name = "orbion"
    owner_user_id = uuid.uuid4()
    task_id = uuid.uuid4()

    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO projects (id, name, description, tenant_id, default_thread_id, created_at) "
            "VALUES ($1, $2, $3, 'default', NULL, NOW())",
            project_id,
            f"del-owner-{project_id.hex[:8]}",
            "test",
        )

    bare_repo = tmp_path / "projects" / str(project_id) / "repo" / f"{repo_name}.git"
    init_bare_repo(bare_repo)
    resolver.register(task_id, project_id, repo_name, owner_user_id, task_status=task_status)
    wt = await svc.create_or_reuse(task_id)
    return task_id, bare_repo, owner_user_id, wt.id


# GW-5.1 delete_by_owner 从 paused 状态放弃 task
async def test_delete_by_owner_from_paused(
    worktree_service: tuple[WorktreeService, StubTaskResolver],
    db_pool: asyncpg.Pool,
    tmp_path: Path,
) -> None:
    svc, resolver = worktree_service
    task_id, bare_repo, owner_id, wt_id = await _create_task_worktree(
        svc, resolver, tmp_path, db_pool, task_status="paused"
    )

    await svc.delete_by_owner(wt_id, owner_id)

    assert not (bare_repo.parent / "worktrees" / f"task_{task_id}").exists()
    async with db_pool.acquire() as conn:
        status = await conn.fetchval("SELECT status FROM worktrees WHERE id = $1", wt_id)
    assert status == "archived"


# GW-5.2 delete_by_owner 从 running 状态放弃 task
async def test_delete_by_owner_from_running(
    worktree_service: tuple[WorktreeService, StubTaskResolver],
    db_pool: asyncpg.Pool,
    tmp_path: Path,
) -> None:
    svc, resolver = worktree_service
    task_id, bare_repo, owner_id, wt_id = await _create_task_worktree(
        svc, resolver, tmp_path, db_pool, task_status="running"
    )

    await svc.delete_by_owner(wt_id, owner_id)

    assert not (bare_repo.parent / "worktrees" / f"task_{task_id}").exists()
    async with db_pool.acquire() as conn:
        status = await conn.fetchval("SELECT status FROM worktrees WHERE id = $1", wt_id)
    assert status == "archived"


# GW-5.3 delete_by_owner 从 timeout 状态放弃 task
# pending 无 worktree 是 AgentRuntime 层逻辑（无 worktree_id 可传），不在本步骤范围
async def test_delete_by_owner_from_timeout(
    worktree_service: tuple[WorktreeService, StubTaskResolver],
    db_pool: asyncpg.Pool,
    tmp_path: Path,
) -> None:
    svc, resolver = worktree_service
    task_id, bare_repo, owner_id, wt_id = await _create_task_worktree(
        svc, resolver, tmp_path, db_pool, task_status="timeout"
    )

    await svc.delete_by_owner(wt_id, owner_id)

    assert not (bare_repo.parent / "worktrees" / f"task_{task_id}").exists()
    async with db_pool.acquire() as conn:
        status = await conn.fetchval("SELECT status FROM worktrees WHERE id = $1", wt_id)
    assert status == "archived"


# GW-5.4 delete_by_owner 非 owner 抛 PermissionError
async def test_delete_by_owner_non_owner_raises_permission(
    worktree_service: tuple[WorktreeService, StubTaskResolver],
    db_pool: asyncpg.Pool,
    tmp_path: Path,
) -> None:
    svc, resolver = worktree_service
    _, _, _, wt_id = await _create_task_worktree(svc, resolver, tmp_path, db_pool, task_status="running")
    non_owner = uuid.uuid4()

    with pytest.raises(PermissionError):
        await svc.delete_by_owner(wt_id, non_owner)

    async with db_pool.acquire() as conn:
        status = await conn.fetchval("SELECT status FROM worktrees WHERE id = $1", wt_id)
    assert status == "active"


# GW-5.5 delete_by_owner 对 completed/cancelled 状态抛 TaskStateError
@pytest.mark.parametrize("forbidden_status", ["completed", "cancelled"])
async def test_delete_by_owner_forbidden_state_raises(
    worktree_service: tuple[WorktreeService, StubTaskResolver],
    db_pool: asyncpg.Pool,
    tmp_path: Path,
    forbidden_status: str,
) -> None:
    svc, resolver = worktree_service
    _, _, owner_id, wt_id = await _create_task_worktree(svc, resolver, tmp_path, db_pool, task_status=forbidden_status)

    with pytest.raises(TaskStateError):
        await svc.delete_by_owner(wt_id, owner_id)

    async with db_pool.acquire() as conn:
        status = await conn.fetchval("SELECT status FROM worktrees WHERE id = $1", wt_id)
    assert status == "active"


# GW-5.6 main worktree 不可删
async def test_delete_by_owner_main_worktree_raises(
    worktree_service: tuple[WorktreeService, StubTaskResolver],
    db_pool: asyncpg.Pool,
    tmp_path: Path,
) -> None:
    svc, _ = worktree_service
    project_id = uuid.uuid4()
    owner_id = uuid.uuid4()
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO projects (id, name, description, tenant_id, default_thread_id, created_at) "
            "VALUES ($1, $2, $3, 'default', NULL, NOW())",
            project_id,
            f"main-del-{project_id.hex[:8]}",
            "test",
        )
        main_wt_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO worktrees (id, project_id, repo_name, worktree_type, branch_name, path, status, "
            "created_by, task_id) VALUES ($1, $2, 'orbion', 'main', 'main', '/tmp/main', 'active', $3, NULL)",
            main_wt_id,
            project_id,
            owner_id,
        )

    with pytest.raises((PermissionError, ValueError)):
        await svc.delete_by_owner(main_wt_id, owner_id)

    async with db_pool.acquire() as conn:
        status = await conn.fetchval("SELECT status FROM worktrees WHERE id = $1", main_wt_id)
    assert status == "active"


# GW-5 补充：worktree_id 不存在抛 WorktreeNotFoundError
async def test_delete_by_owner_nonexistent_worktree_raises(
    worktree_service: tuple[WorktreeService, StubTaskResolver],
) -> None:
    svc, _ = worktree_service
    from app.biz.worktree.worktree_service import WorktreeNotFoundError

    with pytest.raises(WorktreeNotFoundError):
        await svc.delete_by_owner(uuid.uuid4(), uuid.uuid4())
