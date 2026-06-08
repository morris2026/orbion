"""认证依赖注入：get_current_user、require_admin（标准FastAPI Depends链）"""

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.config import Settings, get_settings
from app.hub.auth.models import User
from app.hub.auth.service import JWT_ISS

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


# -- 核心逻辑（纯函数，UT可直接调用） --


def get_current_user_from_token(token: str, settings: Settings) -> User:
    """从JWT token解析当前用户。过期/无效token抛出401。解码时验证iss声明。

    leeway=30s容忍时钟偏移（WSL2时钟同步回跳、多服务器NTP误差），
    符合RFC 7519对时钟偏移容忍的推荐。
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            options={"verify_iss": True},
            issuer=JWT_ISS,
            leeway=30,
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    return User(
        id=payload["sub"],
        username=payload["username"],
        display_name=payload.get("display_name", ""),
        is_admin=payload.get("is_admin", False),
    )


def require_admin(user: User) -> User:
    """要求当前用户是管理员。非管理员抛出403。"""
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


# -- FastAPI Depends链（组合OAuth2 scheme + 核心逻辑） --


async def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    settings: Settings = Depends(get_settings),
) -> User:
    """OAuth2依赖：无token返回401而非422，然后解码JWT返回User"""
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return get_current_user_from_token(token, settings)


async def require_admin_dependency(user: User = Depends(get_current_user)) -> User:
    """组合依赖：先获取当前用户→检查is_admin"""
    return require_admin(user)
