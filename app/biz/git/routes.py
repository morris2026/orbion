"""Git log查询API端点"""

import asyncio
from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Request

from app.biz.git.models import GitLogEntry
from app.biz.git.service import GitService
from app.biz.projects.read_repo import ProjectReadProtocol
from app.hub.auth.dependencies import get_current_user
from app.hub.auth.models import User

router = APIRouter()


async def _get_git_service(request: Request) -> GitService:
    return cast(GitService, request.app.state.git_service)


async def _get_project_read(request: Request) -> ProjectReadProtocol:
    return cast(ProjectReadProtocol, request.app.state.project_read)


@router.get("/{project_id}/git-log", response_model=list[GitLogEntry])
async def get_git_log(
    project_id: str,
    user: User = Depends(get_current_user),
    git_service: GitService = Depends(_get_git_service),
    project_read: ProjectReadProtocol = Depends(_get_project_read),
) -> list[GitLogEntry]:
    """查询项目最近的git commit历史，需项目成员权限"""
    is_member = await project_read.check_member_exists(project_id, user.id)
    if not is_member:
        raise HTTPException(status_code=404, detail="Not a project member")
    # Why: git.Repo.iter_commits是同步阻塞I/O，通过to_thread避免阻塞asyncio事件循环
    commits = await asyncio.to_thread(git_service.get_recent_commits, 10)
    return [GitLogEntry(**c) for c in commits]
