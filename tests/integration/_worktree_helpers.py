"""WorktreeService 测试共享辅助 — bare 仓库初始化 + StubTaskResolver

提取自 test_worktree_service.py / test_worktree_concurrency.py 共用部分（审查 M4）。
"""

from __future__ import annotations

import subprocess
import uuid
from pathlib import Path

from app.biz.worktree.models import TaskContext, TaskResolver

__all__ = ["StubTaskResolver", "init_bare_repo"]


class StubTaskResolver(TaskResolver):
    """内存 TaskResolver — 测试用 task_id → TaskContext 映射"""

    def __init__(self) -> None:
        self._contexts: dict[uuid.UUID, TaskContext] = {}

    def register(self, task_id: uuid.UUID, project_id: uuid.UUID, repo_name: str, owner_user_id: uuid.UUID) -> None:
        self._contexts[task_id] = TaskContext(project_id=project_id, repo_name=repo_name, owner_user_id=owner_user_id)

    async def resolve(self, task_id: uuid.UUID) -> TaskContext:
        if task_id not in self._contexts:
            raise KeyError(f"task {task_id} 未注册")
        return self._contexts[task_id]


def init_bare_repo(path: Path) -> None:
    """初始化 bare 仓库并提交初始 commit 到 main 分支

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
    subprocess.run(["git", "-C", str(tmp), "config", "core.bare", "true"], check=True, capture_output=True)
    subprocess.run(["mv", str(tmp / ".git"), str(path)], check=True, capture_output=True)
    subprocess.run(["rm", "-rf", str(tmp)], check=True, capture_output=True)
