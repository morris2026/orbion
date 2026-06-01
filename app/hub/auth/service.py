"""认证服务：密码哈希、JWT签发、用户CRUD"""

import uuid
from datetime import UTC, datetime, timedelta

import asyncpg
import bcrypt
import jwt

from app.config import Settings

JWT_ISS = "orbion"
JWT_EXPIRY_DAYS = 7

# pool.acquire()返回PoolConnectionProxy，直接连接返回Connection
DbConn = asyncpg.Connection | asyncpg.pool.PoolConnectionProxy


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


# -- 用户CRUD（业务逻辑从routes.py提取） --


async def check_username_exists(conn: DbConn, username: str) -> bool:
    row = await conn.fetchrow("SELECT id FROM users WHERE username = $1", username)
    return row is not None


async def create_user(
    conn: DbConn,
    username: str,
    password_hash: str,
    display_name: str,
    user_status: str,
    is_admin: bool,
) -> asyncpg.Record | None:
    return await conn.fetchrow(
        "INSERT INTO users (username, password_hash, display_name, status, is_admin) "
        "VALUES ($1, $2, $3, $4, $5) RETURNING id, status",
        username,
        password_hash,
        display_name,
        user_status,
        is_admin,
    )


async def get_user_by_username(conn: DbConn, username: str) -> asyncpg.Record | None:
    return await conn.fetchrow(
        "SELECT id, username, display_name, password_hash, status, is_admin FROM users WHERE username = $1",
        username,
    )


async def get_user_by_id(conn: DbConn, user_id: uuid.UUID) -> asyncpg.Record | None:
    return await conn.fetchrow(
        "SELECT id, username, display_name, status, is_admin FROM users WHERE id = $1",
        user_id,
    )


async def update_user_status(conn: DbConn, user_id: uuid.UUID, new_status: str) -> None:
    await conn.execute("UPDATE users SET status = $1 WHERE id = $2", new_status, user_id)


async def list_pending_users(conn: DbConn) -> list[asyncpg.Record]:
    return await conn.fetch(
        "SELECT id, username, display_name, status, created_at FROM users WHERE status = 'pending' ORDER BY created_at"
    )
