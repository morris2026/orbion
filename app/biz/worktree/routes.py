"""Worktree 管理 API + 文件操作 API（worktree 上下文）— 设计 §13"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from app.biz.projects.read_repo import ProjectReadProtocol
from app.biz.worktree.models import Worktree
from app.biz.worktree.worktree_service import (
    TaskStateError,
    WorktreeNotFoundError,
    WorktreeService,
)
from app.hub.auth.dependencies import get_current_user
from app.hub.auth.models import User

router = APIRouter()


class WorktreeOut(BaseModel):
    id: str
    project_id: str
    repo_name: str
    worktree_type: str
    branch_name: str
    path: str
    status: str
    created_by: str
    task_id: str | None
    conflict_regen_count: int


class FileContentOut(BaseModel):
    path: str
    content: str
    mtime: float | None = None
    size: int | None = None


class WriteFileBody(BaseModel):
    content: str


def _worktree_to_out(wt: Worktree) -> WorktreeOut:
    return WorktreeOut(
        id=str(wt.id),
        project_id=str(wt.project_id),
        repo_name=wt.repo_name,
        worktree_type=wt.worktree_type,
        branch_name=wt.branch_name,
        path=wt.path,
        status=wt.status,
        created_by=str(wt.created_by),
        task_id=str(wt.task_id) if wt.task_id else None,
        conflict_regen_count=wt.conflict_regen_count,
    )


def _get_worktree_service(request: Request) -> WorktreeService:
    svc = getattr(request.app.state, "worktree_service", None)
    if svc is None:
        raise HTTPException(status_code=500, detail="WorktreeService 未初始化")
    return cast(WorktreeService, svc)


def _get_project_read(request: Request) -> ProjectReadProtocol:
    return cast(ProjectReadProtocol, request.app.state.project_read)


async def _check_project_member(project_id: str, user: User, project_read: ProjectReadProtocol) -> None:
    is_member = await project_read.check_member_exists(project_id, user.id)
    if not is_member:
        raise HTTPException(status_code=403, detail="Not a project member")


def _validate_file_path(base: Path, file_path: str) -> Path:
    full = (base / file_path).resolve()
    if not full.is_relative_to(base):
        raise HTTPException(status_code=403, detail="路径越界")
    return full


# -- Worktree 管理 API（§13.1）----------------------------------------


@router.get("/{project_id}/worktrees", response_model=list[WorktreeOut])
async def list_worktrees(
    project_id: str,
    user: User = Depends(get_current_user),
    svc: WorktreeService = Depends(_get_worktree_service),
    project_read: ProjectReadProtocol = Depends(_get_project_read),
) -> list[WorktreeOut]:
    await _check_project_member(project_id, user, project_read)
    worktrees = await svc.list_by_project(UUID(project_id))
    return [_worktree_to_out(w) for w in worktrees]


@router.get("/{project_id}/worktrees/{worktree_id}", response_model=WorktreeOut)
async def get_worktree(
    project_id: str,
    worktree_id: UUID,
    user: User = Depends(get_current_user),
    svc: WorktreeService = Depends(_get_worktree_service),
    project_read: ProjectReadProtocol = Depends(_get_project_read),
) -> WorktreeOut:
    await _check_project_member(project_id, user, project_read)
    wt = await svc.get(worktree_id)
    if wt is None:
        raise HTTPException(status_code=404, detail="worktree 不存在")
    return _worktree_to_out(wt)


@router.delete("/{project_id}/worktrees/{worktree_id}", status_code=204)
async def delete_worktree(
    project_id: str,
    worktree_id: UUID,
    user: User = Depends(get_current_user),
    svc: WorktreeService = Depends(_get_worktree_service),
    project_read: ProjectReadProtocol = Depends(_get_project_read),
) -> None:
    await _check_project_member(project_id, user, project_read)
    try:
        await svc.delete_by_owner(worktree_id, UUID(user.id))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except TaskStateError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except WorktreeNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/{project_id}/worktrees/{worktree_id}/merge")
async def merge_worktree(
    project_id: str,
    worktree_id: UUID,
    user: User = Depends(get_current_user),
    svc: WorktreeService = Depends(_get_worktree_service),
    project_read: ProjectReadProtocol = Depends(_get_project_read),
) -> dict[str, Any]:
    await _check_project_member(project_id, user, project_read)
    wt = await svc.get(worktree_id)
    if wt is None or wt.task_id is None:
        raise HTTPException(status_code=404, detail="worktree 不存在或无关联 task")
    try:
        result = await svc.merge(wt.task_id)
    except WorktreeNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return {"success": result.success, "has_conflicts": result.has_conflicts}


# -- 文件操作 API（worktree 上下文，§13.2）-------------------------------


@router.get(
    "/{project_id}/worktrees/{worktree_id}/files",
    response_model=FileContentOut,
)
async def read_worktree_file(
    project_id: str,
    worktree_id: UUID,
    path: str = Query(...),
    user: User = Depends(get_current_user),
    svc: WorktreeService = Depends(_get_worktree_service),
    project_read: ProjectReadProtocol = Depends(_get_project_read),
) -> FileContentOut:
    await _check_project_member(project_id, user, project_read)
    wt = await svc.get(worktree_id)
    if wt is None:
        raise HTTPException(status_code=404, detail="worktree 不存在")
    base = Path(wt.path)
    if not base.exists():
        raise HTTPException(status_code=404, detail="worktree 目录不存在")
    full = _validate_file_path(base, path)
    if not full.exists():
        raise HTTPException(status_code=404, detail=f"文件不存在: {path}")
    try:
        content = full.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        content = ""
    return FileContentOut(path=path, content=content, mtime=os.path.getmtime(full), size=full.stat().st_size)


@router.post(
    "/{project_id}/worktrees/{worktree_id}/files",
    response_model=FileContentOut,
)
async def write_worktree_file(
    project_id: str,
    worktree_id: UUID,
    body: WriteFileBody,
    path: str = Query(...),
    user: User = Depends(get_current_user),
    svc: WorktreeService = Depends(_get_worktree_service),
    project_read: ProjectReadProtocol = Depends(_get_project_read),
) -> FileContentOut:
    await _check_project_member(project_id, user, project_read)
    wt = await svc.get(worktree_id)
    if wt is None:
        raise HTTPException(status_code=404, detail="worktree 不存在")
    base = Path(wt.path)
    if not base.exists():
        raise HTTPException(status_code=404, detail="worktree 目录不存在")
    full = _validate_file_path(base, path)
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(body.content, encoding="utf-8")
    return FileContentOut(path=path, content=body.content, mtime=os.path.getmtime(full), size=full.stat().st_size)


@router.delete("/{project_id}/worktrees/{worktree_id}/files", status_code=204)
async def delete_worktree_file(
    project_id: str,
    worktree_id: UUID,
    path: str = Query(...),
    user: User = Depends(get_current_user),
    svc: WorktreeService = Depends(_get_worktree_service),
    project_read: ProjectReadProtocol = Depends(_get_project_read),
) -> None:
    await _check_project_member(project_id, user, project_read)
    wt = await svc.get(worktree_id)
    if wt is None:
        raise HTTPException(status_code=404, detail="worktree 不存在")
    base = Path(wt.path)
    if not base.exists():
        raise HTTPException(status_code=404, detail="worktree 目录不存在")
    full = _validate_file_path(base, path)
    if not full.exists():
        raise HTTPException(status_code=404, detail=f"文件不存在: {path}")
    full.unlink()


@router.get(
    "/{project_id}/worktrees/{worktree_id}/files/tree",
    response_model=list[dict[str, str]],
)
async def get_worktree_file_tree(
    project_id: str,
    worktree_id: UUID,
    user: User = Depends(get_current_user),
    svc: WorktreeService = Depends(_get_worktree_service),
    project_read: ProjectReadProtocol = Depends(_get_project_read),
) -> list[dict[str, str]]:
    await _check_project_member(project_id, user, project_read)
    wt = await svc.get(worktree_id)
    if wt is None:
        raise HTTPException(status_code=404, detail="worktree 不存在")
    base = Path(wt.path)
    if not base.exists():
        return []
    result: list[dict[str, str]] = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        rel_dir = Path(dirpath).relative_to(base)
        for name in filenames:
            rel = str(rel_dir / name) if str(rel_dir) != "." else name
            result.append({"path": rel, "type": "file", "name": name})
        for name in dirnames:
            rel = str(rel_dir / name) if str(rel_dir) != "." else name
            result.append({"path": rel, "type": "dir", "name": name})
    return result
