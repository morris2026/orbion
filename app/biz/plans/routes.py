"""执行计划审批API端点"""

from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Request

from app.biz.plans.models import PlanApprove, PlanApproveResponse, PlanReject, PlanRejectResponse, PlanResponse
from app.biz.plans.service import PlanService
from app.biz.projects.service import ProjectService
from app.hub.auth.dependencies import get_current_user
from app.hub.auth.models import User
from app.hub.permissions.bitmask import HumanPermission
from app.hub.permissions.compute import compute_permissions

# 计划列表路由——注册在 /projects 前缀下
plan_list_router = APIRouter()

# 计划操作路由——注册在 /plans 前缀下
plan_action_router = APIRouter()


async def _get_plan_service(request: Request) -> PlanService:
    return cast(PlanService, request.app.state.plan_service)


async def _get_project_service(request: Request) -> ProjectService:
    return cast(ProjectService, request.app.state.project_service)


@plan_list_router.get("/{project_id}/plans", response_model=list[PlanResponse])
async def list_plans(
    project_id: str,
    thread_id: str | None = None,
    status: str | None = None,
    user: User = Depends(get_current_user),
    service: PlanService = Depends(_get_plan_service),
    project_service: ProjectService = Depends(_get_project_service),
) -> list[PlanResponse]:
    """列出执行计划，项目成员可查看，可按thread_id和status过滤"""
    # Why: 用VIEW_DISCUSSION位检查而非check_member_exists——与线程模块的成员存在检查模式不同，
    # 但设计文档权限表明确指定此端点需要VIEW_DISCUSSION位，位检查语义更明确，
    # 且为"受限查看者"角色预留了细粒度控制能力
    roles = await project_service.get_member_roles(project_id, user.id)
    if roles is None:
        raise HTTPException(status_code=403, detail="Not a project member")
    if not compute_permissions(roles, HumanPermission.VIEW_DISCUSSION):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    plans = await service.list_plans(project_id, thread_id, status)
    return [PlanResponse(**p) for p in plans]


@plan_action_router.post("/{plan_id}/approve", response_model=PlanApproveResponse)
async def approve_plan(
    plan_id: str,
    request: PlanApprove,
    user: User = Depends(get_current_user),
    service: PlanService = Depends(_get_plan_service),
    project_service: ProjectService = Depends(_get_project_service),
) -> PlanApproveResponse:
    """审批执行计划，需要APPROVE_PLAN权限"""
    # Why: 路径中没有project_id，需从plan数据反查project_id做权限检查
    plan = await service.get_plan_by_id(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="计划不存在")
    project_id = plan["project_id"]

    roles = await project_service.get_member_roles(project_id, user.id)
    if roles is None:
        raise HTTPException(status_code=403, detail="Not a project member")
    if not compute_permissions(roles, HumanPermission.APPROVE_PLAN):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    try:
        result = await service.approve_plan(
            plan_id=plan_id,
            approved_tasks=request.approved_tasks,
            modifications=request.modifications,
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
    return PlanApproveResponse(**result)


@plan_action_router.post("/{plan_id}/reject", response_model=PlanRejectResponse)
async def reject_plan(
    plan_id: str,
    request: PlanReject,
    user: User = Depends(get_current_user),
    service: PlanService = Depends(_get_plan_service),
    project_service: ProjectService = Depends(_get_project_service),
) -> PlanRejectResponse:
    """拒绝执行计划，需要REJECT_PLAN权限"""
    plan = await service.get_plan_by_id(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="计划不存在")
    project_id = plan["project_id"]

    roles = await project_service.get_member_roles(project_id, user.id)
    if roles is None:
        raise HTTPException(status_code=403, detail="Not a project member")
    if not compute_permissions(roles, HumanPermission.REJECT_PLAN):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    try:
        result = await service.reject_plan(
            plan_id=plan_id,
            reason=request.reason,
            suggestions=request.suggestions,
            rejecter_id=user.id,
            rejecter_name=user.display_name,
            project_id=project_id,
        )
    except ValueError as e:
        msg = str(e)
        if "不存在" in msg:
            raise HTTPException(status_code=404, detail=msg)
        if "非法" in msg:
            raise HTTPException(status_code=400, detail=msg)
        raise
    return PlanRejectResponse(**result)
