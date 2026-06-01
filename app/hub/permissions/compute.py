"""权限计算：Deny胜过Allow、require_permission依赖"""

from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Depends, HTTPException

from app.hub.auth.dependencies import get_current_user
from app.hub.auth.models import User
from app.hub.permissions.bitmask import HumanPermission


def compute_permissions(allow_bits: int, permission: int, deny_bits: int = 0) -> bool:
    """Deny永远胜过Allow（包括ADMINISTRATOR），未被deny时ADMINISTRATOR绕过其他权限检查。

    ADMINISTRATOR位是独立的高位(bit 11=2048)，与任何具体权限位不重叠，
    因此不能用位运算隐式绕过——必须显式检查。
    """
    if deny_bits & permission:
        return False
    if allow_bits & HumanPermission.ADMINISTRATOR:
        return True
    return bool(allow_bits & permission)


def require_permission(permission: int) -> Callable[..., Coroutine[Any, Any, bool]]:
    """创建一个FastAPI dependency，检查当前用户是否有指定权限。

    用法：
        @router.post("/plans/{id}/approve")
        async def approve_plan(
            _perm = Depends(require_permission(HumanPermission.APPROVE_PLAN)),
        ):
            ...
    """

    async def check_permission(
        user: User = Depends(get_current_user),
    ) -> bool:
        # MVP只做项目级权限检查——实际查询project_members表获取roles
        # 但project_members表在步骤9才实现，当前依赖只验证JWT层面的is_admin
        # 完整实现在步骤9接入project_members后补充
        if user.is_admin:
            return True

        raise HTTPException(status_code=403, detail="Insufficient permissions")

    return check_permission
