"""Git log查询 + Source Control API端点"""

import asyncio
from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Request

from app.biz.git.models import CommitRequest, GitFileStatus, GitLogEntry, GitStatusResult, StageRequest
from app.biz.git.service import GitService
from app.biz.projects.read_repo import ProjectReadProtocol
from app.hub.auth.dependencies import get_current_user
from app.hub.auth.models import User

router = APIRouter()
sc_router = APIRouter()


async def _get_git_service(request: Request) -> GitService:
    return cast(GitService, request.app.state.git_service)


async def _get_project_read(request: Request) -> ProjectReadProtocol:
    return cast(ProjectReadProtocol, request.app.state.project_read)


def _validate_repo_name(repo_name: str) -> None:
    if "/" in repo_name or "\\" in repo_name or ".." in repo_name:
        raise HTTPException(status_code=400, detail=f"无效的仓库名: {repo_name}")


async def _check_member(project_id: str, user: User, project_read: ProjectReadProtocol) -> None:
    is_member = await project_read.check_member_exists(project_id, user.id)
    if not is_member:
        raise HTTPException(status_code=403, detail="Not a project member")


@router.get("/{project_id}/git-log", response_model=list[GitLogEntry])
async def get_git_log(
    project_id: str,
    repo_name: str,
    user: User = Depends(get_current_user),
    git_service: GitService = Depends(_get_git_service),
    project_read: ProjectReadProtocol = Depends(_get_project_read),
) -> list[GitLogEntry]:
    """查询项目最近的git commit历史，需项目成员权限"""
    await _check_member(project_id, user, project_read)
    commits = await asyncio.to_thread(git_service.get_recent_commits, project_id, repo_name, 10)
    return [GitLogEntry(**c) for c in commits]


@sc_router.get("/{project_id}/repos/{repo_name}/status", response_model=GitStatusResult)
async def get_status(
    project_id: str,
    repo_name: str,
    user: User = Depends(get_current_user),
    git_service: GitService = Depends(_get_git_service),
    project_read: ProjectReadProtocol = Depends(_get_project_read),
) -> GitStatusResult:
    """git status：返回 staged/changes 文件列表"""
    await _check_member(project_id, user, project_read)
    _validate_repo_name(repo_name)
    try:
        result = await asyncio.to_thread(git_service.status, project_id, repo_name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"仓库不存在: {repo_name}")
    return GitStatusResult(
        staged=[GitFileStatus(**f) for f in result["staged"]],
        changes=[GitFileStatus(**f) for f in result["changes"]],
    )


@sc_router.post("/{project_id}/repos/{repo_name}/stage")
async def stage_files(
    project_id: str,
    repo_name: str,
    body: StageRequest,
    user: User = Depends(get_current_user),
    git_service: GitService = Depends(_get_git_service),
    project_read: ProjectReadProtocol = Depends(_get_project_read),
) -> dict[str, str]:
    """stage 文件（git add）"""
    await _check_member(project_id, user, project_read)
    _validate_repo_name(repo_name)
    try:
        await asyncio.to_thread(git_service.stage, project_id, repo_name, body.paths)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"仓库不存在: {repo_name}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "ok"}


@sc_router.post("/{project_id}/repos/{repo_name}/unstage")
async def unstage_files(
    project_id: str,
    repo_name: str,
    body: StageRequest,
    user: User = Depends(get_current_user),
    git_service: GitService = Depends(_get_git_service),
    project_read: ProjectReadProtocol = Depends(_get_project_read),
) -> dict[str, str]:
    """unstage 文件（git reset HEAD）"""
    await _check_member(project_id, user, project_read)
    _validate_repo_name(repo_name)
    try:
        await asyncio.to_thread(git_service.unstage, project_id, repo_name, body.paths)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"仓库不存在: {repo_name}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "ok"}


@sc_router.post("/{project_id}/repos/{repo_name}/commit")
async def commit_changes(
    project_id: str,
    repo_name: str,
    body: CommitRequest,
    user: User = Depends(get_current_user),
    git_service: GitService = Depends(_get_git_service),
    project_read: ProjectReadProtocol = Depends(_get_project_read),
) -> dict[str, str]:
    """commit 已 staged 的文件"""
    await _check_member(project_id, user, project_read)
    _validate_repo_name(repo_name)
    try:
        hexsha = await asyncio.to_thread(git_service.commit, project_id, repo_name, body.message)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"仓库不存在: {repo_name}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"hexsha": hexsha}
