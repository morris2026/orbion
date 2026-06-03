"""任务产出审批API端点"""

from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Request

from app.biz.outputs.models import (
    OutputApprove,
    OutputApproveResponse,
    OutputRequestRevision,
    OutputResponse,
    OutputRevisionResponse,
)
from app.biz.outputs.service import OutputService
from app.biz.projects.service import ProjectService
from app.hub.auth.dependencies import get_current_user
from app.hub.auth.models import User
from app.hub.permissions.bitmask import HumanPermission
from app.hub.permissions.compute import compute_permissions

# 产出列表路由——注册在 /projects 前缀下
output_list_router = APIRouter()

# 产出操作路由——注册在 /outputs 前缀下
output_action_router = APIRouter()


async def _get_output_service(request: Request) -> OutputService:
    return cast(OutputService, request.app.state.output_service)


async def _get_project_service(request: Request) -> ProjectService:
    return cast(ProjectService, request.app.state.project_service)


@output_list_router.get("/{project_id}/outputs", response_model=list[OutputResponse])
async def list_outputs(
    project_id: str,
    plan_id: str | None = None,
    user: User = Depends(get_current_user),
    service: OutputService = Depends(_get_output_service),
    project_service: ProjectService = Depends(_get_project_service),
) -> list[OutputResponse]:
    """列出任务产出，项目成员可查看，可按plan_id过滤"""
    # Why: 用VIEW_DISCUSSION位检查——与计划列表端点一致，语义明确且为细粒度角色预留能力
    roles = await project_service.get_member_roles(project_id, user.id)
    if roles is None:
        raise HTTPException(status_code=403, detail="Not a project member")
    if not compute_permissions(roles, HumanPermission.VIEW_DISCUSSION):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    outputs = await service.list_outputs(project_id, plan_id)
    return [OutputResponse(**o) for o in outputs]


@output_action_router.post("/{output_id}/approve", response_model=OutputApproveResponse)
async def approve_output(
    output_id: str,
    request: OutputApprove,
    user: User = Depends(get_current_user),
    service: OutputService = Depends(_get_output_service),
    project_service: ProjectService = Depends(_get_project_service),
) -> OutputApproveResponse:
    """审批产出通过，需要APPROVE_PLAN权限"""
    # Why: 路径中没有project_id，需从output数据反查project_id做权限检查
    output = await service.get_output_by_id(output_id)
    if output is None:
        raise HTTPException(status_code=404, detail="产出不存在")
    project_id = output["project_id"]

    roles = await project_service.get_member_roles(project_id, user.id)
    if roles is None:
        raise HTTPException(status_code=403, detail="Not a project member")
    # Why: 设计文档指定产出审批使用APPROVE_PLAN权限位（非独立的APPROVE_OUTPUT）
    if not compute_permissions(roles, HumanPermission.APPROVE_PLAN):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    try:
        result = await service.approve_output(
            output_id=output_id,
            feedback=request.feedback,
            approver_id=user.id,
            approver_name=user.display_name,
            project_id=project_id,
        )
    except ValueError as e:
        msg = str(e)
        if "不存在" in msg:
            raise HTTPException(status_code=404, detail=msg)
        if "非法" in msg:
            raise HTTPException(status_code=400, detail=msg)
        raise
    return OutputApproveResponse(**result)


@output_action_router.post("/{output_id}/request-revision", response_model=OutputRevisionResponse)
async def request_revision(
    output_id: str,
    request: OutputRequestRevision,
    user: User = Depends(get_current_user),
    service: OutputService = Depends(_get_output_service),
    project_service: ProjectService = Depends(_get_project_service),
) -> OutputRevisionResponse:
    """要求修改产出，需要CREATE_MESSAGE权限"""
    output = await service.get_output_by_id(output_id)
    if output is None:
        raise HTTPException(status_code=404, detail="产出不存在")
    project_id = output["project_id"]

    roles = await project_service.get_member_roles(project_id, user.id)
    if roles is None:
        raise HTTPException(status_code=403, detail="Not a project member")
    # Why: 设计文档6.3写"认证：同approve"，但端点总览表写"项目成员"——存在矛盾；
    # 端点总览表与最小特权原则更一致（普通Member即可要求修改，无需审批权限），故遵循总览表
    if not compute_permissions(roles, HumanPermission.CREATE_MESSAGE):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    try:
        result = await service.request_revision(
            output_id=output_id,
            issues=request.issues,
            suggestions=request.suggestions,
            requester_id=user.id,
            requester_name=user.display_name,
            project_id=project_id,
        )
    except ValueError as e:
        msg = str(e)
        if "不存在" in msg:
            raise HTTPException(status_code=404, detail=msg)
        if "非法" in msg:
            raise HTTPException(status_code=400, detail=msg)
        raise
    return OutputRevisionResponse(**result)
