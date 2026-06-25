"""WorktreeService API 端点测试 — GW-6.4 ~ GW-6.6

验证 worktree 管理 API（列表 / cancel）+ 文件操作 API（worktree 上下文）。
使用 httpx AsyncClient + 真实 PG + 真实 git。
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from pathlib import Path

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient

from app.biz.git.git_service import GitCommandService
from app.biz.projects.read_repo import load_project_read_impl
from app.biz.projects.service import ProjectService
from app.biz.worktree.worktree_service import WorktreeService
from app.config import Settings, get_settings
from app.hub.auth.repository import UserRepositoryProvider, load_user_repo_provider
from app.hub.auth.service import create_access_token, hash_password
from app.hub.events.bus import InProcessEventBus
from app.hub.events.projections import load_projections_impl
from app.hub.events.store import load_store_impl
from app.main import app

from ._worktree_helpers import StubTaskResolver, init_bare_repo


async def _create_user(provider: UserRepositoryProvider, username: str) -> dict[str, str]:
    async with provider.scoped() as repo:
        user = await repo.create_user(username, hash_password("testpass123"), username.capitalize(), "active", False)
    token = create_access_token(
        user_id=user.id, username=user.username, display_name=user.display_name, is_admin=False, settings=get_settings()
    )
    return {"id": user.id, "token": token}


async def _create_project(client: AsyncClient, token: str, name: str) -> str:
    resp = await client.post("/projects", json={"name": name}, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    return str(resp.json()["id"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def worktree_api_client(
    tmp_path: Path,
) -> AsyncGenerator[tuple[AsyncClient, StubTaskResolver, asyncpg.Pool], None]:
    """设置 app.state 含 WorktreeService，返回 (client, resolver, pool)"""
    settings = get_settings()
    event_bus = InProcessEventBus()

    store_cls = load_store_impl(settings.event_store)
    event_store = store_cls()
    await event_store.connect()

    proj_cls = load_projections_impl(settings.event_projections)
    projections = proj_cls(event_bus)
    await projections.connect()

    pool = await asyncpg.create_pool(settings.postgres.url, min_size=1, max_size=5)
    resolver = StubTaskResolver()
    wt_settings = Settings(jwt_secret=settings.jwt_secret, root_dir=str(tmp_path))
    git_cmd = GitCommandService()
    worktree_service = WorktreeService(git_cmd, wt_settings, pool, resolver, event_bus=event_bus)

    user_repo_provider_cls = load_user_repo_provider(settings.user_repo)
    user_repo_provider = user_repo_provider_cls()
    await user_repo_provider.connect()

    project_read_cls = load_project_read_impl(settings.project_read)
    project_read = project_read_cls()
    await project_read.connect()

    app.state.event_store = event_store
    app.state.event_bus = event_bus
    app.state.event_projections = projections
    app.state.user_repo_provider = user_repo_provider
    app.state.project_read = project_read
    app.state.project_service = ProjectService(event_store, event_bus, project_read, settings)
    app.state.worktree_service = worktree_service
    app.state.worktree_pool = pool

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c, resolver, pool

    await project_read.close()
    await user_repo_provider.close()
    await projections.close()
    await event_store.close()
    await pool.close()


# GW-6.4 GET /worktrees 列表
async def test_get_worktrees_list(
    worktree_api_client: tuple[AsyncClient, StubTaskResolver, asyncpg.Pool],
    tmp_path: Path,
    user_repo_provider: UserRepositoryProvider,
    event_bus: InProcessEventBus,
) -> None:
    client, resolver, pool = worktree_api_client
    user = await _create_user(user_repo_provider, "wtuser1")
    project_id = await _create_project(client, user["token"], "WTListProject")
    await event_bus.wait_for_pending()

    # 插入 main worktree + 2 task worktree
    owner_id = uuid.uuid4()
    async with pool.acquire() as conn:
        for i in range(2):
            task_id = uuid.uuid4()
            await conn.execute(
                "INSERT INTO worktrees (id, project_id, repo_name, worktree_type, branch_name, path, status, "
                "created_by, task_id) VALUES ($1, $2, 'orbion', 'task', $3, $4, 'active', $5, $6)",
                uuid.uuid4(),
                project_id,
                f"task/{task_id}",
                f"/tmp/wt_{i}",
                owner_id,
                task_id,
            )
        await conn.execute(
            "INSERT INTO worktrees (id, project_id, repo_name, worktree_type, branch_name, path, status, "
            "created_by, task_id) VALUES ($1, $2, 'orbion', 'main', 'main', '/tmp/main', 'active', $3, NULL)",
            uuid.uuid4(),
            project_id,
            owner_id,
        )

    resp = await client.get(f"/projects/{project_id}/worktrees", headers=_auth(user["token"]))

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 3
    types = {w["worktree_type"] for w in data}
    assert types == {"main", "task"}
    for w in data:
        assert "id" in w
        assert "status" in w
        assert "branch_name" in w


# GW-6.5 DELETE /worktrees/{id} cancel
async def test_delete_worktree_cancel(
    worktree_api_client: tuple[AsyncClient, StubTaskResolver, asyncpg.Pool],
    tmp_path: Path,
    user_repo_provider: UserRepositoryProvider,
    event_bus: InProcessEventBus,
) -> None:
    client, resolver, pool = worktree_api_client
    user = await _create_user(user_repo_provider, "wtuser2")
    project_id = await _create_project(client, user["token"], "WTDeleteProject")
    await event_bus.wait_for_pending()

    # 设置 bare repo + main worktree + task worktree
    repo_name = "orbion"
    bare_repo = tmp_path / "projects" / str(project_id) / "repo" / f"{repo_name}.git"
    worktrees_root = tmp_path / "projects" / str(project_id) / "repo" / "worktrees"
    init_bare_repo(bare_repo)
    worktrees_root.mkdir(parents=True, exist_ok=True)
    subprocess_run = __import__("subprocess")
    subprocess_run.run(
        ["git", "-C", str(bare_repo), "worktree", "add", str(worktrees_root / "main"), "main"],
        check=True,
        capture_output=True,
    )

    # 注册 task + 创建 worktree
    task_id = uuid.uuid4()
    owner_id = uuid.uuid4()
    resolver.register(task_id, uuid.UUID(project_id), repo_name, owner_id, task_status="running")
    wt_settings = Settings(jwt_secret=get_settings().jwt_secret, root_dir=str(tmp_path))
    svc = WorktreeService(GitCommandService(), wt_settings, pool, resolver)
    wt = await svc.create_or_reuse(task_id)

    # DELETE 需要认证为 owner——但 owner_id 是随机 UUID 不是注册用户
    # 用 user["id"] 作为 owner 重新注册
    resolver._contexts[task_id] = resolver._contexts[task_id]  # already registered with owner_id
    # 更新 worktree 的 created_by 为 user["id"]
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE worktrees SET created_by = $1 WHERE id = $2",
            uuid.UUID(user["id"]),
            wt.id,
        )

    resp = await client.delete(f"/projects/{project_id}/worktrees/{wt.id}", headers=_auth(user["token"]))

    assert resp.status_code == 204
    async with pool.acquire() as conn:
        status = await conn.fetchval("SELECT status FROM worktrees WHERE id = $1", wt.id)
    assert status == "archived"


# GW-6.6 文件操作 API 含 worktree 上下文
async def test_get_file_from_worktree(
    worktree_api_client: tuple[AsyncClient, StubTaskResolver, asyncpg.Pool],
    tmp_path: Path,
    user_repo_provider: UserRepositoryProvider,
    event_bus: InProcessEventBus,
) -> None:
    client, resolver, pool = worktree_api_client
    user = await _create_user(user_repo_provider, "wtuser3")
    project_id = await _create_project(client, user["token"], "WTFileProject")
    await event_bus.wait_for_pending()

    # 设置 bare repo + main worktree + task worktree（含文件）
    repo_name = "orbion"
    bare_repo = tmp_path / "projects" / str(project_id) / "repo" / f"{repo_name}.git"
    worktrees_root = tmp_path / "projects" / str(project_id) / "repo" / "worktrees"
    init_bare_repo(bare_repo)
    worktrees_root.mkdir(parents=True, exist_ok=True)
    subprocess_run = __import__("subprocess")
    subprocess_run.run(
        ["git", "-C", str(bare_repo), "worktree", "add", str(worktrees_root / "main"), "main"],
        check=True,
        capture_output=True,
    )

    task_id = uuid.uuid4()
    owner_id = uuid.uuid4()
    resolver.register(task_id, uuid.UUID(project_id), repo_name, owner_id, task_status="running")
    wt_settings = Settings(jwt_secret=get_settings().jwt_secret, root_dir=str(tmp_path))
    svc = WorktreeService(GitCommandService(), wt_settings, pool, resolver)
    wt = await svc.create_or_reuse(task_id)

    # 在 task worktree 写文件
    task_wt_path = worktrees_root / f"task_{task_id}"
    (task_wt_path / "README.md").write_text("# task worktree content\n")

    resp = await client.get(
        f"/projects/{project_id}/worktrees/{wt.id}/files",
        params={"path": "README.md"},
        headers=_auth(user["token"]),
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["content"] == "# task worktree content\n"
    assert data["mtime"] is not None
