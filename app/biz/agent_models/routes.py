"""AgentModelMapping 路由 — 用户级 + 项目级"""

from typing import cast

from fastapi import APIRouter, Body, Depends, HTTPException, Request

from app.biz.agent_models.service import AgentModelMappingService
from app.biz.projects.read_repo import ProjectReadProtocol
from app.hub.auth.dependencies import get_current_user
from app.hub.auth.models import User


def _get_service(request: Request) -> AgentModelMappingService:
    return cast(AgentModelMappingService, request.app.state.agent_model_mapping_service)


async def _get_project_read(request: Request) -> ProjectReadProtocol:
    return cast(ProjectReadProtocol, request.app.state.project_read)


async def _check_member(project_id: str, user: User, project_read: ProjectReadProtocol) -> None:
    """跨项目越权防护：非项目成员返回 403（与 git/routes.py 一致）"""
    if not await project_read.check_member_exists(project_id, user.id):
        raise HTTPException(status_code=403, detail="Not a project member")


user_router = APIRouter(prefix="/users/me/agent-models", tags=["agent-models"])


@user_router.get("")
async def get_user_mapping(
    user: User = Depends(get_current_user),
    service: AgentModelMappingService = Depends(_get_service),
) -> dict[str, str]:
    return await service.get_user_mapping(user.id)


@user_router.put("")
async def set_user_mapping(
    payload: dict[str, str] = Body(...),
    user: User = Depends(get_current_user),
    service: AgentModelMappingService = Depends(_get_service),
) -> dict[str, str]:
    return await service.set_user_mapping(user.id, payload)


project_router = APIRouter(prefix="/projects/{project_id}/agent-model-override", tags=["agent-models"])


@project_router.get("")
async def get_project_override(
    project_id: str,
    user: User = Depends(get_current_user),
    service: AgentModelMappingService = Depends(_get_service),
    project_read: ProjectReadProtocol = Depends(_get_project_read),
) -> dict[str, str]:
    await _check_member(project_id, user, project_read)
    return service.get_project_override(project_id)


@project_router.put("")
async def set_project_override(
    project_id: str,
    payload: dict[str, str] = Body(...),
    user: User = Depends(get_current_user),
    service: AgentModelMappingService = Depends(_get_service),
    project_read: ProjectReadProtocol = Depends(_get_project_read),
) -> dict[str, str]:
    await _check_member(project_id, user, project_read)
    return service.set_project_override(project_id, payload)


@project_router.delete("/{agent_type}")
async def delete_project_override(
    project_id: str,
    agent_type: str,
    user: User = Depends(get_current_user),
    service: AgentModelMappingService = Depends(_get_service),
    project_read: ProjectReadProtocol = Depends(_get_project_read),
) -> dict[str, str]:
    await _check_member(project_id, user, project_read)
    return service.delete_project_override(project_id, agent_type)
