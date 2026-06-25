"""WorktreeService 合并流程 + 冲突重生成测试 — GW-4.1 ~ GW-4.4

使用真实 git 二进制 + tmp_path bare 仓库 + 真实 PostgreSQL worktrees 表，
验证 merge 成功流转、冲突自动重生成、超限抛 WorktreeConflictError、MAX 可配。
"""

from __future__ import annotations

import subprocess
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path

import asyncpg
import pytest

from app.biz.git.git_service import GitCommandService
from app.biz.worktree.worktree_service import (
    WorktreeConflictError,
    WorktreeService,
)
from app.config import Settings

from ._worktree_helpers import StubTaskResolver, init_bare_repo


def _commit_in_worktree(wt_path: Path, filename: str, content: str, msg: str) -> None:
    """在 worktree 目录里 add + commit"""
    (wt_path / filename).write_text(content)
    subprocess.run(["git", "-C", str(wt_path), "add", filename], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(wt_path), "-c", "user.email=t@orbion", "-c", "user.name=t", "commit", "-m", msg],
        check=True,
        capture_output=True,
    )


def _setup_main_worktree(bare_repo: Path, worktrees_root: Path) -> Path:
    """从 bare 仓库创建 main worktree（设计 §2 的 worktrees/main/）"""
    worktrees_root.mkdir(parents=True, exist_ok=True)
    main_wt = worktrees_root / "main"
    subprocess.run(
        ["git", "-C", str(bare_repo), "worktree", "add", str(main_wt), "main"],
        check=True,
        capture_output=True,
    )
    return main_wt


@pytest.fixture
async def db_pool() -> AsyncGenerator[asyncpg.Pool, None]:
    from app.config import get_settings

    pool = await asyncpg.create_pool(get_settings().postgres.url, min_size=1, max_size=5)
    yield pool
    await pool.close()


@pytest.fixture
async def worktree_service(db_pool: asyncpg.Pool, tmp_path: Path) -> AsyncGenerator[WorktreeService, None]:
    settings = Settings(jwt_secret="test-secret-32bytes-for-jwt-hs256", root_dir=str(tmp_path))
    resolver = StubTaskResolver()
    svc = WorktreeService(GitCommandService(), settings, db_pool, resolver)
    yield svc


@pytest.fixture
async def project_with_main_and_task(
    db_pool: asyncpg.Pool,
    tmp_path: Path,
    worktree_service: WorktreeService,
) -> tuple[uuid.UUID, uuid.UUID, Path, Path]:
    """创建项目 + bare 仓库 + main worktree + 注册 task + 创建 task worktree

    返回 (task_id, project_id, bare_repo, main_worktree)
    """
    project_id = uuid.uuid4()
    repo_name = "orbion"
    owner_user_id = uuid.uuid4()
    task_id = uuid.uuid4()

    # 插入 project 行
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO projects (id, name, description, tenant_id, default_thread_id, created_at) "
            "VALUES ($1, $2, $3, 'default', NULL, NOW())",
            project_id,
            f"merge-test-{project_id.hex[:8]}",
            "test",
        )

    # bare 仓库 + main worktree
    bare_repo = tmp_path / "projects" / str(project_id) / "repo" / f"{repo_name}.git"
    worktrees_root = tmp_path / "projects" / str(project_id) / "repo" / "worktrees"
    init_bare_repo(bare_repo)
    main_wt = _setup_main_worktree(bare_repo, worktrees_root)

    # 注册 task + 创建 task worktree
    worktree_service.task_resolver.register(task_id, project_id, repo_name, owner_user_id)  # type: ignore[attr-defined]
    await worktree_service.create_or_reuse(task_id)

    return task_id, project_id, bare_repo, main_wt


# GW-4.1 merge 成功流转
async def test_merge_success(
    worktree_service: WorktreeService,
    project_with_main_and_task: tuple[uuid.UUID, uuid.UUID, Path, Path],
) -> None:
    task_id, _, bare_repo, main_wt = project_with_main_and_task
    # 在 task worktree 里加 commit
    task_wt = bare_repo.parent / "worktrees" / f"task_{task_id}"
    _commit_in_worktree(task_wt, "feature.py", "print('hi')\n", "feat: add feature")

    result = await worktree_service.merge(task_id)

    assert result.success is True
    assert result.has_conflicts is False
    # main worktree 含 task 的 commit（feature.py 存在）
    assert (main_wt / "feature.py").exists()
    # task worktree 已 archived（文件系统目录删除 + DB status）
    assert not task_wt.exists()
    async with worktree_service.pool.acquire() as conn:
        status = await conn.fetchval("SELECT status FROM worktrees WHERE task_id = $1", task_id)
    assert status == "archived"


# GW-4.2 merge 冲突自动重生成
async def test_merge_conflict_triggers_regenerate(
    worktree_service: WorktreeService,
    project_with_main_and_task: tuple[uuid.UUID, uuid.UUID, Path, Path],
) -> None:
    task_id, _, bare_repo, main_wt = project_with_main_and_task

    # 先在 task worktree 改 README.md（基于原始 main）
    task_wt = bare_repo.parent / "worktrees" / f"task_{task_id}"
    _commit_in_worktree(task_wt, "README.md", "# task changed\n", "task: update readme")

    # 推进 main（改 README.md 同位置）→ 制造冲突
    _commit_in_worktree(main_wt, "README.md", "# main changed\n", "main: update readme")

    result = await worktree_service.merge(task_id)

    # 冲突被检测到
    assert result.success is False
    assert result.has_conflicts is True
    # main 回到合并前状态（README.md 仍是 main 的修改）
    assert (main_wt / "README.md").read_text() == "# main changed\n"

    # regenerate 被触发：新 worktree 基于 latest main 创建
    # conflict_regen_count 递增到 1
    async with worktree_service.pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT status, conflict_regen_count FROM worktrees WHERE task_id = $1 AND status != 'archived'",
            task_id,
        )
    assert row is not None, "regenerate 未创建新 worktree"
    assert row["status"] == "active"
    assert row["conflict_regen_count"] == 1


# GW-4.3 重生成次数超限抛 WorktreeConflictError
async def test_merge_conflict_exceeds_max_raises(
    worktree_service: WorktreeService,
    project_with_main_and_task: tuple[uuid.UUID, uuid.UUID, Path, Path],
) -> None:
    task_id, _, bare_repo, main_wt = project_with_main_and_task

    # 预设 conflict_regen_count = MAX（默认 3）→ 下次冲突应超限
    async with worktree_service.pool.acquire() as conn:
        await conn.execute(
            "UPDATE worktrees SET conflict_regen_count = 3 WHERE task_id = $1 AND status != 'archived'",
            task_id,
        )

    # 制造冲突
    task_wt = bare_repo.parent / "worktrees" / f"task_{task_id}"
    _commit_in_worktree(task_wt, "README.md", "# task changed\n", "task: update readme")
    _commit_in_worktree(main_wt, "README.md", "# main changed\n", "main: update readme")

    # 超限应抛 WorktreeConflictError
    with pytest.raises(WorktreeConflictError):
        await worktree_service.merge(task_id)

    # M2：验证 main 回到合并前状态（git merge --abort 已执行）
    assert (main_wt / "README.md").read_text() == "# main changed\n"
    # I3：超限后旧 worktree 应被清理（archive），重新 dispatch 走"首次创建"分支
    assert not task_wt.exists()
    async with worktree_service.pool.acquire() as conn:
        status = await conn.fetchval("SELECT status FROM worktrees WHERE task_id = $1", task_id)
    assert status == "archived"


# GW-4.4 MAX_CONFLICT_REGENERATIONS 可配
async def test_max_conflict_regenerations_configurable(db_pool: asyncpg.Pool, tmp_path: Path) -> None:
    """MAX=5 时前 5 次正常重生成，第 6 次抛错"""
    settings = Settings(jwt_secret="test-secret-32bytes-for-jwt-hs256", root_dir=str(tmp_path))
    resolver = StubTaskResolver()
    svc = WorktreeService(GitCommandService(), settings, db_pool, resolver, max_conflict_regenerations=5)

    project_id = uuid.uuid4()
    repo_name = "orbion"
    owner_user_id = uuid.uuid4()
    task_id = uuid.uuid4()

    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO projects (id, name, description, tenant_id, default_thread_id, created_at) "
            "VALUES ($1, $2, $3, 'default', NULL, NOW())",
            project_id,
            f"max-test-{project_id.hex[:8]}",
            "test",
        )

    bare_repo = tmp_path / "projects" / str(project_id) / "repo" / f"{repo_name}.git"
    worktrees_root = tmp_path / "projects" / str(project_id) / "repo" / "worktrees"
    init_bare_repo(bare_repo)
    main_wt = _setup_main_worktree(bare_repo, worktrees_root)

    resolver.register(task_id, project_id, repo_name, owner_user_id)
    await svc.create_or_reuse(task_id)

    # 预设 count = 5（MAX=5）→ 下次冲突超限
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE worktrees SET conflict_regen_count = 5 WHERE task_id = $1 AND status != 'archived'",
            task_id,
        )

    task_wt = bare_repo.parent / "worktrees" / f"task_{task_id}"
    _commit_in_worktree(task_wt, "README.md", "# task\n", "task")
    _commit_in_worktree(main_wt, "README.md", "# main\n", "main")

    # MAX=5 + count=5 → 超限抛错
    with pytest.raises(WorktreeConflictError):
        await svc.merge(task_id)

    # 验证 MAX=5 允许到 5（count=4 时不超限，能正常 regenerate）
    # 用另一个 task 验证
    task2_id = uuid.uuid4()
    resolver.register(task2_id, project_id, repo_name, owner_user_id)
    await svc.create_or_reuse(task2_id)
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE worktrees SET conflict_regen_count = 4 WHERE task_id = $1 AND status != 'archived'",
            task2_id,
        )
    task2_wt = bare_repo.parent / "worktrees" / f"task_{task2_id}"
    _commit_in_worktree(task2_wt, "other.py", "# task2\n", "task2")
    _commit_in_worktree(main_wt, "other_main.py", "# main2\n", "main2")

    # count=4 < MAX=5 → 不超限，正常 merge（不同文件，不冲突）
    result = await svc.merge(task2_id)
    assert result.success is True
