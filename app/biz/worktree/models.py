"""WorktreeService 领域模型 — Worktree 数据结构 + TaskContext + TaskResolver 协议

设计文档：docs/specs/1.10-mvp-git-worktree-model.md §6.4、§11
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

WorktreeType = Literal["main", "task"]
WorktreeStatus = Literal["active", "conflicting", "archived"]


@dataclass
class Worktree:
    """worktrees 表行映射"""

    id: uuid.UUID
    project_id: uuid.UUID
    repo_name: str
    worktree_type: WorktreeType
    branch_name: str
    path: str
    status: WorktreeStatus
    created_by: uuid.UUID
    task_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


@dataclass
class TaskContext:
    """task 解析结果——create_or_reuse 根据 task_id 查到的上下文

    Why 需要 TaskResolver：create_or_reuse(task_id) 只接收 task_id，但创建 worktree
    需要 project_id + repo_name（定位 bare 仓库）+ owner_user_id（worktrees 表
    created_by 字段）。这些信息存于 tasks 表（agent-runtime §3.4），本步骤通过
    TaskResolver 协议注入，未来 agent-runtime 重构时实现 PostgresTaskResolver。
    """

    project_id: uuid.UUID
    repo_name: str
    owner_user_id: uuid.UUID


class TaskResolver(Protocol):
    """task_id → TaskContext 解析协议

    实现方需提供 async resolve(task_id) 返回 TaskContext；
    task 不存在时应抛 KeyError 或 NotFoundError（由调用方决定语义）。
    """

    async def resolve(self, task_id: uuid.UUID) -> TaskContext: ...
