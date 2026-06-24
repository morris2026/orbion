"""WorktreeService 核心测试 — GW-2.2 ~ GW-2.8

使用真实 git 二进制 + tmp_path bare 仓库 + 真实 PostgreSQL worktrees 表，
验证 create_or_reuse / archive / get / list_by_project 与 task 状态映射。
"""

from __future__ import annotations

import subprocess
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path

import asyncpg
import pytest

from app.biz.git.git_service import GitCommandService
from app.biz.worktree.worktree_service import TaskNotFoundError, WorktreeService
from app.config import Settings

from ._worktree_helpers import StubTaskResolver, init_bare_repo


@pytest.fixture
def git_command_service() -> GitCommandService:
    return GitCommandService()


@pytest.fixture
def task_resolver() -> StubTaskResolver:
    return StubTaskResolver()


@pytest.fixture
async def db_pool() -> AsyncGenerator[asyncpg.Pool, None]:
    """真实 PG 连接池 — 根 conftest 已 TRUNCATE 表"""
    from app.config import get_settings

    pool = await asyncpg.create_pool(get_settings().postgres.url, min_size=1, max_size=5)
    yield pool
    await pool.close()


@pytest.fixture
async def worktree_service(
    git_command_service: GitCommandService,
    task_resolver: StubTaskResolver,
    db_pool: asyncpg.Pool,
    tmp_path: Path,
) -> AsyncGenerator[WorktreeService, None]:
    """WorktreeService 实例 + tmp_path 作为 root_dir（隔离文件系统）"""
    settings = Settings(jwt_secret="test-secret-32bytes-for-jwt-hs256", root_dir=str(tmp_path))
    svc = WorktreeService(git_command_service, settings, db_pool, task_resolver)
    yield svc


@pytest.fixture
async def project_with_bare_repo(
    db_pool: asyncpg.Pool, tmp_path: Path, task_resolver: StubTaskResolver
) -> tuple[uuid.UUID, uuid.UUID, Path]:
    """创建项目记录 + bare 仓库 + 注册 task context

    返回 (task_id, project_id, bare_repo_path)
    """
    project_id = uuid.uuid4()
    repo_name = "orbion"
    owner_user_id = uuid.uuid4()

    # 在 PG 插入 project 行（FK 约束）
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO projects (id, name, description, tenant_id, default_thread_id, created_at) "
            "VALUES ($1, $2, $3, 'default', NULL, NOW())",
            project_id,
            f"wt-test-{project_id.hex[:8]}",
            "test project",
        )

    # bare 仓库路径 = settings.project_dir(project_id)/repo/{repo_name}.git
    bare_repo = tmp_path / "projects" / str(project_id) / "repo" / f"{repo_name}.git"
    init_bare_repo(bare_repo)

    # 注册一个 task
    task_id = uuid.uuid4()
    task_resolver.register(task_id, project_id, repo_name, owner_user_id)
    return task_id, project_id, bare_repo


# GW-2.2 create_or_reuse 首次创建
async def test_create_or_reuse_first_creates_worktree(
    worktree_service: WorktreeService,
    project_with_bare_repo: tuple[uuid.UUID, uuid.UUID, Path],
) -> None:
    task_id, project_id, bare_repo = project_with_bare_repo

    worktree = await worktree_service.create_or_reuse(task_id)

    assert worktree.task_id == task_id
    assert worktree.worktree_type == "task"
    assert worktree.status == "active"
    assert worktree.branch_name == f"task/{task_id}"
    # 文件系统 worktrees/task_{task_id}/ 存在
    expected_path = bare_repo.parent / "worktrees" / f"task_{task_id}"
    assert expected_path.is_dir()
    # git branch task/{task_id} 已创建
    branches = subprocess.run(
        ["git", "-C", str(bare_repo), "branch", "--list"], capture_output=True, text=True, check=True
    ).stdout
    assert f"task/{task_id}" in branches


# GW-2.3 create_or_reuse 重做复用
async def test_create_or_reuse_reuses_existing(
    worktree_service: WorktreeService,
    project_with_bare_repo: tuple[uuid.UUID, uuid.UUID, Path],
) -> None:
    task_id, _, bare_repo = project_with_bare_repo

    first = await worktree_service.create_or_reuse(task_id)
    # 模拟 task 内已有产出
    worktree_dir = bare_repo.parent / "worktrees" / f"task_{task_id}"
    (worktree_dir / "artifact.md").write_text("半成品\n")

    second = await worktree_service.create_or_reuse(task_id)

    # 同一 worktree 记录（id 一致）
    assert second.id == first.id
    # 文件系统目录未变（半成品保留）
    assert (worktree_dir / "artifact.md").read_text() == "半成品\n"
    # worktrees 表无新增（count=1）
    async with worktree_service.pool.acquire() as conn:
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM worktrees WHERE task_id = $1 AND status != 'archived'", task_id
        )
    assert count == 1


# GW-2.4 archive 清理 worktree
async def test_archive_removes_worktree_and_branch(
    worktree_service: WorktreeService,
    project_with_bare_repo: tuple[uuid.UUID, uuid.UUID, Path],
) -> None:
    task_id, _, bare_repo = project_with_bare_repo
    await worktree_service.create_or_reuse(task_id)
    worktree_dir = bare_repo.parent / "worktrees" / f"task_{task_id}"
    assert worktree_dir.is_dir()

    await worktree_service.archive(task_id)

    # 文件系统目录已删
    assert not worktree_dir.exists()
    # git branch task/{task_id} 已删
    branches = subprocess.run(
        ["git", "-C", str(bare_repo), "branch", "--list"], capture_output=True, text=True, check=True
    ).stdout
    assert f"task/{task_id}" not in branches
    # worktrees 表 status='archived'
    async with worktree_service.pool.acquire() as conn:
        status = await conn.fetchval("SELECT status FROM worktrees WHERE task_id = $1", task_id)
    assert status == "archived"


# archive 对不存在的 task 为 no-op（pending 首次无 worktree）
async def test_archive_no_op_for_nonexistent_task(worktree_service: WorktreeService) -> None:
    """设计 §6.4 delete_by_owner：pending 首次无 worktree 时 archive 为 no-op"""
    random_task_id = uuid.uuid4()

    # 不抛异常
    await worktree_service.archive(random_task_id)

    # worktrees 表无该 task 记录
    async with worktree_service.pool.acquire() as conn:
        count = await conn.fetchval("SELECT COUNT(*) FROM worktrees WHERE task_id = $1", random_task_id)
    assert count == 0


# GW-2.5 get 查询 worktree
async def test_get_returns_worktree_by_id(
    worktree_service: WorktreeService,
    project_with_bare_repo: tuple[uuid.UUID, uuid.UUID, Path],
) -> None:
    task_id, project_id, _ = project_with_bare_repo
    created = await worktree_service.create_or_reuse(task_id)

    fetched = await worktree_service.get(created.id)

    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.task_id == task_id
    assert fetched.project_id == project_id
    assert fetched.worktree_type == "task"
    assert fetched.status == "active"


async def test_get_returns_none_for_nonexistent_id(worktree_service: WorktreeService) -> None:
    result = await worktree_service.get(uuid.uuid4())
    assert result is None


# GW-2.6 list_by_project 列出项目 worktree
async def test_list_by_project_returns_all_worktrees(
    worktree_service: WorktreeService,
    project_with_bare_repo: tuple[uuid.UUID, uuid.UUID, Path],
    task_resolver: StubTaskResolver,
) -> None:
    task_id, project_id, _ = project_with_bare_repo
    # 已有 1 个 task worktree（project_with_bare_repo 注册了 1 个 task）
    await worktree_service.create_or_reuse(task_id)

    # 再加 1 个 task worktree
    task2_id = uuid.uuid4()
    task_resolver.register(task2_id, project_id, "orbion", uuid.uuid4())
    await worktree_service.create_or_reuse(task2_id)

    # 再加 1 个 main worktree（直接插入表，main 由项目初始化创建，非 WorktreeService.create_or_reuse）
    async with worktree_service.pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO worktrees (id, project_id, repo_name, worktree_type, branch_name, path, status, "
            "created_by, task_id, created_at, updated_at) "
            "VALUES ($1, $2, 'orbion', 'main', 'main', '/tmp/main', 'active', $3, NULL, NOW(), NOW())",
            uuid.uuid4(),
            project_id,
            uuid.uuid4(),
        )

    worktrees = await worktree_service.list_by_project(project_id)

    assert len(worktrees) == 3
    types = {w.worktree_type for w in worktrees}
    assert types == {"main", "task"}
    # task worktree 按 created_at 倒序（最新 task2 在前）
    task_wts = [w for w in worktrees if w.worktree_type == "task"]
    assert len(task_wts) == 2
    assert task_wts[0].created_at >= task_wts[1].created_at


# GW-2.8 task 6 状态与 worktree 状态映射
async def test_task_state_to_worktree_state_mapping(
    worktree_service: WorktreeService,
    project_with_bare_repo: tuple[uuid.UUID, uuid.UUID, Path],
) -> None:
    """模拟 task 状态流转：pending → running → paused → running → completed → cancelled

    每步验证 worktree 状态：
    - pending（首次）：worktree 不存在
    - running：create_or_reuse 创建 active worktree
    - paused：无 WorktreeService 调用，worktree 保留（仍 active）
    - running（resume）：create_or_reuse 复用，仍 active
    - completed：无 WorktreeService 调用，worktree 仍 active
    - cancelled：archive 后 status='archived'
    """
    task_id, _, _ = project_with_bare_repo

    # pending（首次）：无 worktree
    async with worktree_service.pool.acquire() as conn:
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM worktrees WHERE task_id = $1 AND status != 'archived'", task_id
        )
    assert count == 0, "pending 状态不应有 worktree"

    # running：create_or_reuse 创建 active
    wt_running = await worktree_service.create_or_reuse(task_id)
    assert wt_running.status == "active"

    # paused：无调用，worktree 保留
    wt_paused = await worktree_service.get(wt_running.id)
    assert wt_paused is not None
    assert wt_paused.status == "active"

    # running（resume）：create_or_reuse 复用
    wt_resumed = await worktree_service.create_or_reuse(task_id)
    assert wt_resumed.id == wt_running.id
    assert wt_resumed.status == "active"

    # completed：无调用，worktree 仍 active
    wt_completed = await worktree_service.get(wt_running.id)
    assert wt_completed is not None
    assert wt_completed.status == "active"

    # cancelled：archive
    await worktree_service.archive(task_id)
    wt_cancelled = await worktree_service.get(wt_running.id)
    assert wt_cancelled is not None
    assert wt_cancelled.status == "archived"


# I4 error path：task 未注册抛 TaskNotFoundError
async def test_create_or_reuse_unregistered_task_raises_not_found(
    worktree_service: WorktreeService,
) -> None:
    """task_id 未在 TaskResolver 注册时抛 TaskNotFoundError，而非 KeyError 透传"""
    random_task_id = uuid.uuid4()

    with pytest.raises(TaskNotFoundError):
        await worktree_service.create_or_reuse(random_task_id)
