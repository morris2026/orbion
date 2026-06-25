"""WorktreeService 事件发布测试 — GW-6.1 ~ GW-6.3

验证 WorktreeService 在 create_or_reuse / merge / merge 冲突时发布对应事件。
使用 InProcessEventBus + 真实 git + 真实 PG worktrees 表。
"""

from __future__ import annotations

import subprocess
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path

import asyncpg
import pytest

from app.biz.git.git_service import GitCommandService
from app.biz.worktree.worktree_service import WorktreeService
from app.config import Settings
from app.hub.events.bus import InProcessEventBus
from app.hub.events.types import Event

from ._worktree_helpers import StubTaskResolver, init_bare_repo


def _commit_in_worktree(wt_path: Path, filename: str, content: str, msg: str) -> None:
    (wt_path / filename).write_text(content)
    subprocess.run(["git", "-C", str(wt_path), "add", filename], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(wt_path), "-c", "user.email=t@orbion", "-c", "user.name=t", "commit", "-m", msg],
        check=True,
        capture_output=True,
    )


def _setup_main_worktree(bare_repo: Path, worktrees_root: Path) -> Path:
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
async def event_bus() -> InProcessEventBus:
    return InProcessEventBus()


@pytest.fixture
async def worktree_service(
    db_pool: asyncpg.Pool, tmp_path: Path, event_bus: InProcessEventBus
) -> AsyncGenerator[WorktreeService, None]:
    settings = Settings(jwt_secret="test-secret-32bytes-for-jwt-hs256", root_dir=str(tmp_path))
    resolver = StubTaskResolver()
    svc = WorktreeService(GitCommandService(), settings, db_pool, resolver, event_bus=event_bus)
    yield svc


async def _setup_project(
    db_pool: asyncpg.Pool, resolver: StubTaskResolver, tmp_path: Path
) -> tuple[uuid.UUID, uuid.UUID, Path, Path]:
    project_id = uuid.uuid4()
    repo_name = "orbion"
    owner_user_id = uuid.uuid4()

    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO projects (id, name, description, tenant_id, default_thread_id, created_at) "
            "VALUES ($1, $2, $3, 'default', NULL, NOW())",
            project_id,
            f"evt-test-{project_id.hex[:8]}",
            "test",
        )

    bare_repo = tmp_path / "projects" / str(project_id) / "repo" / f"{repo_name}.git"
    worktrees_root = tmp_path / "projects" / str(project_id) / "repo" / "worktrees"
    init_bare_repo(bare_repo)
    main_wt = _setup_main_worktree(bare_repo, worktrees_root)

    # 注册一个 task
    task_id = uuid.uuid4()
    resolver.register(task_id, project_id, repo_name, owner_user_id, task_status="running")
    return task_id, project_id, bare_repo, main_wt


def _capture_events(bus: InProcessEventBus, event_type: str) -> list[Event]:
    """订阅事件类型，返回捕获的事件列表"""
    captured: list[Event] = []

    async def handler(event: Event) -> None:
        captured.append(event)

    bus.subscribe(event_type, handler)
    return captured


# GW-6.1 WorktreeCreated 事件发布
async def test_worktree_created_event_published(
    worktree_service: WorktreeService,
    db_pool: asyncpg.Pool,
    tmp_path: Path,
    event_bus: InProcessEventBus,
) -> None:
    resolver: StubTaskResolver = worktree_service.task_resolver  # type: ignore[assignment]
    task_id, project_id, _, _ = await _setup_project(db_pool, resolver, tmp_path)

    captured = _capture_events(event_bus, "WorktreeCreated")

    wt = await worktree_service.create_or_reuse(task_id)
    await event_bus.wait_for_pending()

    assert len(captured) == 1
    event = captured[0]
    assert event.event_type == "WorktreeCreated"
    assert event.project_id == str(project_id)
    assert event.payload["worktree_id"] == str(wt.id)
    assert event.payload["type"] == "task"
    assert event.payload["branch_name"] == f"task/{task_id}"


# GW-6.2 WorktreeMerged 事件发布
async def test_worktree_merged_event_published(
    worktree_service: WorktreeService,
    db_pool: asyncpg.Pool,
    tmp_path: Path,
    event_bus: InProcessEventBus,
) -> None:
    resolver: StubTaskResolver = worktree_service.task_resolver  # type: ignore[assignment]
    task_id, _, bare_repo, main_wt = await _setup_project(db_pool, resolver, tmp_path)
    wt = await worktree_service.create_or_reuse(task_id)

    # 在 task worktree 加 commit
    task_wt = bare_repo.parent / "worktrees" / f"task_{task_id}"
    _commit_in_worktree(task_wt, "feature.py", "print('hi')\n", "feat")

    captured = _capture_events(event_bus, "WorktreeMerged")

    await worktree_service.merge(task_id)
    await event_bus.wait_for_pending()

    assert len(captured) == 1
    event = captured[0]
    assert event.event_type == "WorktreeMerged"
    assert event.payload["worktree_id"] == str(wt.id)
    assert event.payload["target_branch"] == "main"


# GW-6.3 WorktreeConflictDetected 事件发布
async def test_worktree_conflict_detected_event_published(
    worktree_service: WorktreeService,
    db_pool: asyncpg.Pool,
    tmp_path: Path,
    event_bus: InProcessEventBus,
) -> None:
    resolver: StubTaskResolver = worktree_service.task_resolver  # type: ignore[assignment]
    task_id, _, bare_repo, main_wt = await _setup_project(db_pool, resolver, tmp_path)
    wt = await worktree_service.create_or_reuse(task_id)

    # 制造冲突
    task_wt = bare_repo.parent / "worktrees" / f"task_{task_id}"
    _commit_in_worktree(task_wt, "README.md", "# task\n", "task")
    _commit_in_worktree(main_wt, "README.md", "# main\n", "main")

    captured = _capture_events(event_bus, "WorktreeConflictDetected")

    await worktree_service.merge(task_id)
    await event_bus.wait_for_pending()

    assert len(captured) == 1
    event = captured[0]
    assert event.event_type == "WorktreeConflictDetected"
    assert event.payload["worktree_id"] == str(wt.id)
    assert "README.md" in event.payload["conflict_files"]
