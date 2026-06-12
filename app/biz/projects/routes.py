"""项目与成员管理API端点"""

from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Request

from app.biz.projects.models import (
    MemberAdd,
    MemberListItem,
    MemberResponse,
    ProjectCreate,
    ProjectListItem,
    ProjectResponse,
)
from app.biz.projects.service import ProjectService
from app.hub.auth.dependencies import get_current_user
from app.hub.auth.models import User
from app.hub.auth.repository import UserRepositoryProvider
from app.hub.permissions.bitmask import HumanPermission
from app.hub.permissions.compute import compute_permissions

router = APIRouter()


async def _get_project_service(request: Request) -> ProjectService:
    return cast(ProjectService, request.app.state.project_service)


async def _get_user_repo_provider(request: Request) -> UserRepositoryProvider:
    return cast(UserRepositoryProvider, request.app.state.user_repo_provider)


@router.post("", response_model=ProjectResponse)
async def create_project(
    request: ProjectCreate,
    user: User = Depends(get_current_user),
    service: ProjectService = Depends(_get_project_service),
) -> ProjectResponse:
    """创建项目，创建者自动成为Owner"""
    try:
        project = await service.create_project(request.name, request.description, user)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return ProjectResponse(**project)


@router.get("", response_model=list[ProjectListItem])
async def list_projects(
    user: User = Depends(get_current_user),
    service: ProjectService = Depends(_get_project_service),
) -> list[ProjectListItem]:
    """列出当前用户参与的项目"""
    projects = await service.list_projects(user.id)
    return [ProjectListItem(**p) for p in projects]


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: str,
    user: User = Depends(get_current_user),
    service: ProjectService = Depends(_get_project_service),
) -> ProjectResponse:
    """获取项目详情，仅成员可访问"""
    project = await service.get_project(project_id, user.id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found or not a member")
    return ProjectResponse(**project)


@router.delete("/{project_id}")
async def delete_project(
    project_id: str,
    user: User = Depends(get_current_user),
    service: ProjectService = Depends(_get_project_service),
) -> dict[str, str]:
    """删除项目，需要DELETE_PROJECT权限"""
    try:
        success = await service.delete_project(project_id, user.id)
    except PermissionError:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    if not success:
        raise HTTPException(status_code=404, detail="Project not found or not a member")
    return {"status": "deleted"}


@router.post("/{project_id}/members", response_model=MemberResponse)
async def add_member(
    project_id: str,
    request: MemberAdd,
    user: User = Depends(get_current_user),
    service: ProjectService = Depends(_get_project_service),
    user_repo_provider: UserRepositoryProvider = Depends(_get_user_repo_provider),
) -> MemberResponse:
    """添加成员到项目，需要MANAGE_MEMBERS权限"""
    # 项目级权限检查：查询roles + compute_permissions
    roles = await service.get_member_roles(project_id, user.id)
    if roles is None:
        raise HTTPException(status_code=404, detail="Not a project member")
    if not compute_permissions(roles, HumanPermission.MANAGE_MEMBERS):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    # 查询目标用户信息
    async with user_repo_provider.scoped() as repo:
        target_user = await repo.get_user_by_id(request.user_id)
    if target_user is None:
        raise HTTPException(status_code=404, detail="Target user not found")

    try:
        result = await service.add_member(project_id, request.user_id, request.role, target_user.display_name, user.id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return MemberResponse(**result)


@router.get("/{project_id}/members", response_model=list[MemberListItem])
async def list_members(
    project_id: str,
    user: User = Depends(get_current_user),
    service: ProjectService = Depends(_get_project_service),
) -> list[MemberListItem]:
    """列出项目所有成员，仅项目成员可访问"""
    is_member = await service.get_member_roles(project_id, user.id)
    if is_member is None:
        raise HTTPException(status_code=404, detail="Not a project member")
    members = await service.list_members(project_id)
    return [MemberListItem(**m) for m in members]
