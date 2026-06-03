"""Agent管理API端点"""

from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Request

from app.biz.agents.declarations import BUILTIN_AGENT_DECLARATIONS
from app.biz.agents.models import AgentCreate, AgentResponse, AgentStatus
from app.biz.agents.runtime import AgentRuntime
from app.biz.agents.service import AgentService
from app.biz.projects.read_repo import ProjectReadProtocol
from app.biz.projects.service import ProjectService
from app.hub.auth.dependencies import get_current_user
from app.hub.auth.models import User
from app.hub.permissions.bitmask import HumanPermission
from app.hub.permissions.compute import compute_permissions

router = APIRouter()


def _get_agent_service(request: Request) -> AgentService:
    return cast(AgentService, request.app.state.agent_service)


def _get_project_service(request: Request) -> ProjectService:
    return cast(ProjectService, request.app.state.project_service)


def _get_project_read(request: Request) -> ProjectReadProtocol:
    return cast(ProjectReadProtocol, request.app.state.project_read)


def _get_agent_runtime(request: Request) -> AgentRuntime:
    return cast(AgentRuntime, request.app.state.agent_runtime)


@router.post("/{project_id}/agents", response_model=AgentResponse)
async def register_agent(
    project_id: str,
    body: AgentCreate,
    user: User = Depends(get_current_user),
    service: AgentService = Depends(_get_agent_service),
    project_service: ProjectService = Depends(_get_project_service),
) -> AgentResponse:
    roles = await project_service.get_member_roles(project_id, user.id)
    if roles is None:
        raise HTTPException(status_code=403, detail="Not a project member")
    if not compute_permissions(roles, HumanPermission.MANAGE_AGENTS):
        raise HTTPException(status_code=403, detail="Insufficient permissions: MANAGE_AGENTS required")
    try:
        result = await service.register_agent(project_id, body.agent_type, body.model_id, body.display_name, user)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return AgentResponse(**result)


@router.get("/{project_id}/agents", response_model=list[AgentResponse])
async def list_agents(
    project_id: str,
    user: User = Depends(get_current_user),
    project_read: ProjectReadProtocol = Depends(_get_project_read),
) -> list[AgentResponse]:
    """列出项目所有Agent——需要项目成员权限"""
    if not await project_read.check_member_exists(project_id, user.id):
        raise HTTPException(status_code=403, detail="Not a project member")
    agents = await project_read.list_agents(project_id)
    for agent in agents:
        agent_type: str = agent["agent_type"]
        decl = BUILTIN_AGENT_DECLARATIONS.get(agent_type)
        agent["subscribed_events"] = decl.subscribed_events if decl else []
    return [AgentResponse(**a) for a in agents]


@router.get("/{project_id}/agents/{agent_id}/status", response_model=AgentStatus)
async def get_agent_status(
    project_id: str,
    agent_id: str,
    user: User = Depends(get_current_user),
    project_read: ProjectReadProtocol = Depends(_get_project_read),
    runtime: AgentRuntime = Depends(_get_agent_runtime),
) -> AgentStatus:
    if not await project_read.check_member_exists(project_id, user.id):
        raise HTTPException(status_code=403, detail="Not a project member")
    agent_member = await project_read.get_agent(project_id, agent_id)
    if agent_member is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    agent_type = agent_member["agent_type"]
    status_data = runtime.get_agent_status(project_id, agent_type)
    if status_data is None:
        return AgentStatus(
            agent_id=agent_id,
            status=agent_member.get("status", "idle"),
            current_task=None,
            completed_count=0,
            error_count=0,
            last_execution_at=None,
        )
    return AgentStatus(**status_data)
