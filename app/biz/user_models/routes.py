"""UserModel 路由 — /users/me/models CRUD"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from fastapi import APIRouter, Depends, HTTPException, Request

from app.biz.user_models.models import UserModelCreate, UserModelResponse, UserModelUpdate
from app.biz.user_models.service import UserModelInUseError, UserModelNotFoundError, UserModelService
from app.hub.auth.dependencies import get_current_user
from app.hub.auth.models import User

if TYPE_CHECKING:
    from app.biz.agent_models.service import AgentModelMappingService


def _get_service(request: Request) -> UserModelService:
    return cast(UserModelService, request.app.state.user_model_service)


def _get_agent_model_mapping_service(request: Request) -> AgentModelMappingService:
    """延迟 import 避免循环依赖"""
    from app.biz.agent_models.service import AgentModelMappingService

    return cast(AgentModelMappingService, request.app.state.agent_model_mapping_service)


router = APIRouter(prefix="/users/me/models", tags=["user-models"])


@router.get("", response_model=list[UserModelResponse])
async def list_models(
    user: User = Depends(get_current_user),
    service: UserModelService = Depends(_get_service),
) -> list[UserModelResponse]:
    return await service.list_models(user.id)


@router.post("", response_model=UserModelResponse, status_code=201)
async def create_model(
    request: UserModelCreate,
    user: User = Depends(get_current_user),
    service: UserModelService = Depends(_get_service),
) -> UserModelResponse:
    try:
        return await service.create_model(user.id, request)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e


@router.get("/{model_id}", response_model=UserModelResponse)
async def get_model(
    model_id: str,
    user: User = Depends(get_current_user),
    service: UserModelService = Depends(_get_service),
) -> UserModelResponse:
    try:
        return await service.get_model(user.id, model_id)
    except UserModelNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"UserModel '{model_id}' 不存在") from e


@router.put("/{model_id}", response_model=UserModelResponse)
async def update_model(
    model_id: str,
    request: UserModelUpdate,
    user: User = Depends(get_current_user),
    service: UserModelService = Depends(_get_service),
) -> UserModelResponse:
    try:
        return await service.update_model(user.id, model_id, request)
    except UserModelNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"UserModel '{model_id}' 不存在") from e


@router.delete("/{model_id}", status_code=204)
async def delete_model(
    model_id: str,
    user: User = Depends(get_current_user),
    service: UserModelService = Depends(_get_service),
    mapping_service: AgentModelMappingService = Depends(_get_agent_model_mapping_service),
) -> None:
    referrers = await mapping_service.find_referrers(user.id, model_id)
    try:
        await service.delete_model(user.id, model_id, referrers)
    except UserModelInUseError as e:
        raise HTTPException(
            status_code=409,
            detail=f"UserModel '{model_id}' 被 {e.referrers} 引用，禁止删除",
        ) from e
    except UserModelNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"UserModel '{model_id}' 不存在") from e
