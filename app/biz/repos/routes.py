"""仓库管理 API 端点"""

import asyncio
from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Request

from app.biz.projects.read_repo import ProjectReadProtocol
from app.biz.repos.models import AddRepoRequest, RepoInfo
from app.biz.repos.service import RepoService
from app.hub.auth.dependencies import get_current_user
from app.hub.auth.models import User

router = APIRouter()


def _get_repo_service(request: Request) -> RepoService:
    return cast(RepoService, request.app.state.repo_service)


def _get_project_read(request: Request) -> ProjectReadProtocol:
    return cast(ProjectReadProtocol, request.app.state.project_read)


@router.get("/{project_id}/repos", response_model=list[RepoInfo])
async def list_repos(
    project_id: str,
    user: User = Depends(get_current_user),
    repo_service: RepoService = Depends(_get_repo_service),
    project_read: ProjectReadProtocol = Depends(_get_project_read),
) -> list[RepoInfo]:
    is_member = await project_read.check_member_exists(project_id, user.id)
    if not is_member:
        raise HTTPException(status_code=403, detail="Not a project member")
    repos = await asyncio.to_thread(repo_service.scan_repos, project_id)
    return [RepoInfo(name=r["name"]) for r in repos]


@router.post("/{project_id}/repos", response_model=RepoInfo, status_code=201)
async def add_repo(
    project_id: str,
    body: AddRepoRequest,
    user: User = Depends(get_current_user),
    repo_service: RepoService = Depends(_get_repo_service),
    project_read: ProjectReadProtocol = Depends(_get_project_read),
) -> RepoInfo:
    is_member = await project_read.check_member_exists(project_id, user.id)
    if not is_member:
        raise HTTPException(status_code=403, detail="Not a project member")
    # 获取默认线程 ID 用于发送系统消息
    project = await project_read.get_project(project_id, user.id)
    thread_id = project.get("default_thread_id") if project else None
    result = await repo_service.add_repo(project_id, url=body.url, name=body.name, user_id=user.id, thread_id=thread_id)
    if "error" in result:
        detail = result.get("error", "添加仓库失败")
        raise HTTPException(status_code=400, detail=detail)
    return RepoInfo(name=result["name"])


@router.delete("/{project_id}/repos/{repo_name}", status_code=200)
async def delete_repo(
    project_id: str,
    repo_name: str,
    user: User = Depends(get_current_user),
    repo_service: RepoService = Depends(_get_repo_service),
    project_read: ProjectReadProtocol = Depends(_get_project_read),
) -> dict[str, str]:
    is_member = await project_read.check_member_exists(project_id, user.id)
    if not is_member:
        raise HTTPException(status_code=403, detail="Not a project member")
    if "/" in repo_name or "\\" in repo_name or ".." in repo_name:
        raise HTTPException(status_code=400, detail=f"无效的仓库名: {repo_name}")
    try:
        deleted = await asyncio.to_thread(repo_service.delete_repo, project_id, repo_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not deleted:
        raise HTTPException(status_code=404, detail=f"仓库不存在: {repo_name}")
    return {"name": repo_name}
