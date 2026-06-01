"""认证服务：密码哈希、JWT签发"""

from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.config import Settings

JWT_ISS = "orbion"
JWT_EXPIRY_DAYS = 7


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def create_access_token(
    user_id: str,
    username: str,
    display_name: str,
    is_admin: bool,
    settings: Settings,
) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "username": username,
        "display_name": display_name,
        "is_admin": is_admin,
        "iss": JWT_ISS,
        "exp": now + timedelta(days=JWT_EXPIRY_DAYS),
        "iat": now,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
