"""GitCommandService 命令封装测试 — GW-1.2 ~ GW-1.6 + error path 覆盖

使用真实 git 二进制 + tmp_path 下的 bare 仓库，验证 GitCommandService 对
worktree add/remove、branch 创建/删除、merge 成功/冲突、fetch 的封装行为。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from app.biz.git.git_service import GitCommandService, MergeResult, WorktreeResult


def _init_bare_repo(path: Path) -> None:
    """初始化一个 bare 仓库并提交一个初始 commit 到 main 分支

    先 init 非 bare 仓库提交初始 commit，再 convert to bare（保留 HEAD 指向 main）。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp_src")
    tmp.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", "main", str(tmp)], check=True, capture_output=True)
    (tmp / "README.md").write_text("# seed\n")
    subprocess.run(["git", "-C", str(tmp), "add", "README.md"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(tmp), "-c", "user.email=seed@orbion", "-c", "user.name=seed", "commit", "-m", "seed"],
        check=True,
        capture_output=True,
    )
    # convert to bare：移动 .git 到目标路径并配置 bare=true
    subprocess.run(["git", "-C", str(tmp), "config", "core.bare", "true"], check=True, capture_output=True)
    subprocess.run(["mv", str(tmp / ".git"), str(path)], check=True, capture_output=True)
    subprocess.run(["rm", "-rf", str(tmp)], check=True, capture_output=True)


def _commit(repo_path: Path, filename: str, content: str, message: str) -> None:
    """在普通 worktree 路径上 add + commit"""
    (repo_path / filename).write_text(content)
    subprocess.run(["git", "-C", str(repo_path), "add", filename], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo_path), "-c", "user.email=t@orbion", "-c", "user.name=t", "commit", "-m", message],
        check=True,
        capture_output=True,
    )


@pytest.fixture
def git_service() -> GitCommandService:
    return GitCommandService()


@pytest.fixture
def bare_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "orbion.git"
    _init_bare_repo(repo)
    return repo


# GW-1.2 GitService worktree add 封装
def test_worktree_add_creates_worktree_and_branch(
    git_service: GitCommandService, bare_repo: Path, tmp_path: Path
) -> None:
    worktree_path = tmp_path / "worktrees" / "task_001"
    worktree_path.parent.mkdir(parents=True, exist_ok=True)

    result = git_service.worktree_add(str(bare_repo), str(worktree_path), "task/001", "main")

    assert isinstance(result, WorktreeResult)
    assert result.success is True
    assert worktree_path.is_dir()
    listing = subprocess.run(
        ["git", "-C", str(bare_repo), "worktree", "list"], capture_output=True, text=True, check=True
    ).stdout
    assert "task/001" in listing


# GW-1.3 GitService worktree remove 封装
def test_worktree_remove_deletes_worktree(git_service: GitCommandService, bare_repo: Path, tmp_path: Path) -> None:
    worktree_path = tmp_path / "worktrees" / "task_001"
    worktree_path.parent.mkdir(parents=True, exist_ok=True)
    git_service.worktree_add(str(bare_repo), str(worktree_path), "task/001", "main")

    result = git_service.worktree_remove(str(bare_repo), str(worktree_path))

    assert isinstance(result, WorktreeResult)
    assert result.success is True
    assert not worktree_path.exists()
    listing = subprocess.run(
        ["git", "-C", str(bare_repo), "worktree", "list"], capture_output=True, text=True, check=True
    ).stdout
    assert str(worktree_path) not in listing


# worktree_remove error path：不存在的 worktree 返回 success=False
def test_worktree_remove_nonexistent_returns_error(
    git_service: GitCommandService, bare_repo: Path, tmp_path: Path
) -> None:
    nonexistent = tmp_path / "worktrees" / "ghost"

    result = git_service.worktree_remove(str(bare_repo), str(nonexistent))

    assert result.success is False
    assert result.error  # 非空错误信息


# GW-1.4 GitService branch 创建与删除
def test_branch_create_and_delete(git_service: GitCommandService, bare_repo: Path) -> None:
    git_service.branch_create(str(bare_repo), "task/001", "main")
    branches = subprocess.run(
        ["git", "-C", str(bare_repo), "branch", "--list"], capture_output=True, text=True, check=True
    ).stdout
    assert "task/001" in branches

    git_service.branch_delete(str(bare_repo), "task/001")
    branches = subprocess.run(
        ["git", "-C", str(bare_repo), "branch", "--list"], capture_output=True, text=True, check=True
    ).stdout
    assert "task/001" not in branches


# branch_delete 默认 force=False：未合并分支应被拒绝
def test_branch_delete_default_refuses_unmerged(
    git_service: GitCommandService, bare_repo: Path, tmp_path: Path
) -> None:
    task_wt = tmp_path / "worktrees" / "task_001"
    git_service.worktree_add(str(bare_repo), str(task_wt), "task/001", "main")
    # 在 task/001 上加 commit，相对 main 是未合并状态
    _commit(task_wt, "feature.py", "print('hi')\n", "feat: add feature")

    result = git_service.branch_delete(str(bare_repo), "task/001")  # 默认 force=False

    assert result.success is False
    # force=True 时应成功（需先移除占用该分支的 worktree）
    git_service.worktree_remove(str(bare_repo), str(task_wt), force=True)
    force_result = git_service.branch_delete(str(bare_repo), "task/001", force=True)
    assert force_result.success is True


# GW-1.5 GitService merge 成功
def test_merge_success(git_service: GitCommandService, bare_repo: Path, tmp_path: Path) -> None:
    main_wt = tmp_path / "worktrees" / "main"
    main_wt.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "-C", str(bare_repo), "worktree", "add", str(main_wt), "main"],
        check=True,
        capture_output=True,
    )
    task_wt = tmp_path / "worktrees" / "task_001"
    git_service.worktree_add(str(bare_repo), str(task_wt), "task/001", "main")
    _commit(task_wt, "feature.py", "print('hi')\n", "feat: add feature")

    result = git_service.merge(str(main_wt), "task/001")

    assert isinstance(result, MergeResult)
    assert result.success is True
    assert result.has_conflicts is False
    assert (main_wt / "README.md").exists()
    assert (main_wt / "feature.py").exists()


# GW-1.6 GitService merge 冲突自动 abort
def test_merge_conflict_aborts_and_reports_files(
    git_service: GitCommandService, bare_repo: Path, tmp_path: Path
) -> None:
    # 先创建 task worktree（基于原 main），改同位置
    task_wt = tmp_path / "worktrees" / "task_001"
    git_service.worktree_add(str(bare_repo), str(task_wt), "task/001", "main")
    _commit(task_wt, "README.md", "# task changed\n", "task: update readme")
    # 之后 main 推进，改 README.md 同位置
    main_wt = tmp_path / "worktrees" / "main"
    main_wt.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "-C", str(bare_repo), "worktree", "add", str(main_wt), "main"],
        check=True,
        capture_output=True,
    )
    _commit(main_wt, "README.md", "# main changed\n", "main: update readme")

    result = git_service.merge(str(main_wt), "task/001")

    assert isinstance(result, MergeResult)
    assert result.success is False
    assert result.has_conflicts is True
    assert "README.md" in result.conflict_files
    # merge 自动 abort，main 回到合并前状态
    assert (main_wt / "README.md").read_text() == "# main changed\n"


# merge 非冲突错误路径：合并不存在的分支
def test_merge_nonexistent_branch_returns_error(
    git_service: GitCommandService, bare_repo: Path, tmp_path: Path
) -> None:
    main_wt = tmp_path / "worktrees" / "main"
    main_wt.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "-C", str(bare_repo), "worktree", "add", str(main_wt), "main"],
        check=True,
        capture_output=True,
    )

    result = git_service.merge(str(main_wt), "nonexistent/branch")

    assert result.success is False
    assert result.has_conflicts is False
    assert result.error


# fetch 薄封装：MVP 无远端时返回 success=False（git fetch 失败），但封装层不抛异常
def test_fetch_wraps_subprocess(git_service: GitCommandService, bare_repo: Path) -> None:
    result = git_service.fetch(str(bare_repo), remote="origin")

    # 无远端配置，git fetch 必失败；封装层应返回结构化结果而非抛异常
    assert isinstance(result, WorktreeResult)
    assert result.success is False
    assert result.error
