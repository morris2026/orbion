"""注册策略抽象与Admin审批实现"""

from typing import Protocol, runtime_checkable

from app.hub.auth.models import RegistrationDecision, UserRegister
from app.hub.auth.repository import UserRepositoryProtocol


@runtime_checkable
class RegistrationPolicy(Protocol):
    """注册策略Protocol，使审批流程可替换"""

    async def evaluate(
        self,
        request: UserRegister,
        repo: UserRepositoryProtocol,
    ) -> RegistrationDecision: ...


class AdminApprovalPolicy:
    """MVP注册策略：首个用户自动审批+is_admin，后续用户pending"""

    async def evaluate(
        self,
        request: UserRegister,
        repo: UserRepositoryProtocol,
    ) -> RegistrationDecision:
        is_first_user = not await repo.has_active_users()

        if is_first_user:
            return RegistrationDecision(
                status="active",
                is_admin=True,
                message="Auto-approved as the first admin",
            )
        return RegistrationDecision(
            status="pending",
            is_admin=False,
            message="Registration submitted, awaiting admin approval",
        )
