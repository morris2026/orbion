from typing import cast

from fastapi import APIRouter, Depends, Request

from app.biz.credentials.models import CreateCredentialRequest, CredentialResponse
from app.biz.credentials.service import CredentialService
from app.hub.auth.dependencies import get_current_user
from app.hub.auth.models import User


def _get_credential_service(request: Request) -> CredentialService:
    return cast(CredentialService, request.app.state.credential_service)


router = APIRouter(prefix="/users/me/credentials", tags=["credentials"])


@router.get("", response_model=list[CredentialResponse])
async def list_credentials(
    user: User = Depends(get_current_user),
    service: CredentialService = Depends(_get_credential_service),
) -> list[CredentialResponse]:
    return service.list_credentials(user.id)


@router.post("", response_model=CredentialResponse, status_code=201)
async def create_credential(
    request: CreateCredentialRequest,
    user: User = Depends(get_current_user),
    service: CredentialService = Depends(_get_credential_service),
) -> CredentialResponse:
    return service.create_credential(user.id, request)


@router.delete("/{credential_id}", status_code=204)
async def delete_credential(
    credential_id: str,
    user: User = Depends(get_current_user),
    service: CredentialService = Depends(_get_credential_service),
) -> None:
    service.delete_credential(user.id, credential_id)
