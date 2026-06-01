"""PostgresUserRepository — PostgreSQL users表持久化实现"""

import uuid
from types import TracebackType
from typing import Any

import asyncpg

from app.hub.auth.repository import PendingUserRecord, UserRecord, UserRepositoryProtocol


class PostgresUserRepository(UserRepositoryProtocol):
    """PostgreSQL users表持久化实现

    每个实例=一个事务作用域，使用async context manager管理生命周期：
    async with repo:
        ... CRUD operations ...
    正常退出 → commit；异常退出 → rollback
    """

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool
        # asyncpg缺少类型stub，内部状态使用Any
        self._conn: Any = None
        self._tx: Any = None

    async def __aenter__(self) -> "PostgresUserRepository":
        self._conn = await self._pool.acquire()
        try:
            self._tx = self._conn.transaction()
            await self._tx.__aenter__()
        except BaseException:
            # tx.__aenter__失败时Python不会调用__aexit__，需手动释放连接
            await self._pool.release(self._conn)
            self._conn = None
            raise
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        # asyncpg.transaction().__aexit__ 自动 commit（无异常）或 rollback（有异常）
        # try/finally 保证连接释放：tx.__aexit__ 失败时（如提交时连接断开）仍需归还连接
        try:
            if self._tx is not None:
                await self._tx.__aexit__(exc_type, exc_val, exc_tb)
                self._tx = None
        finally:
            if self._conn is not None:
                await self._pool.release(self._conn)
                self._conn = None

    # -- CRUD 实现 --

    def _ensure_open(self) -> None:
        if self._conn is None:
            raise RuntimeError("PostgresUserRepository 未进入或已退出 async context manager")

    async def has_active_users(self) -> bool:
        self._ensure_open()
        row = await self._conn.fetchrow("SELECT COUNT(*) AS cnt FROM users WHERE status = 'active'")
        return int(row["cnt"]) > 0

    async def check_username_exists(self, username: str) -> bool:
        self._ensure_open()
        row = await self._conn.fetchrow("SELECT id FROM users WHERE username = $1", username)
        return row is not None

    async def create_user(
        self,
        username: str,
        password_hash: str,
        display_name: str,
        user_status: str,
        is_admin: bool,
    ) -> UserRecord:
        self._ensure_open()
        row = await self._conn.fetchrow(
            "INSERT INTO users (username, password_hash, display_name, status, is_admin) "
            "VALUES ($1, $2, $3, $4, $5) RETURNING id, username, display_name, password_hash, status, is_admin",
            username,
            password_hash,
            display_name,
            user_status,
            is_admin,
        )
        # INSERT RETURNING 总返回一行，None 表示数据库异常
        if row is None:
            raise RuntimeError("INSERT RETURNING returned no row — unexpected database failure")
        return _row_to_user_record(row)

    async def get_user_by_username(self, username: str) -> UserRecord | None:
        self._ensure_open()
        row = await self._conn.fetchrow(
            "SELECT id, username, display_name, password_hash, status, is_admin FROM users WHERE username = $1",
            username,
        )
        if row is None:
            return None
        return _row_to_user_record(row)

    async def get_user_by_id(self, user_id: str) -> UserRecord | None:
        self._ensure_open()
        row = await self._conn.fetchrow(
            "SELECT id, username, display_name, password_hash, status, is_admin FROM users WHERE id = $1",
            uuid.UUID(user_id),
        )
        if row is None:
            return None
        return _row_to_user_record(row)

    async def update_user_status(self, user_id: str, new_status: str) -> None:
        self._ensure_open()
        await self._conn.execute("UPDATE users SET status = $1 WHERE id = $2", new_status, uuid.UUID(user_id))

    async def list_pending_users(self) -> list[PendingUserRecord]:
        self._ensure_open()
        rows = await self._conn.fetch(
            "SELECT id, username, display_name, status, created_at "
            "FROM users WHERE status = 'pending' ORDER BY created_at"
        )
        return [_row_to_pending_record(row) for row in rows]


def _row_to_user_record(row: asyncpg.Record) -> UserRecord:
    return UserRecord(
        id=str(row["id"]),
        username=row["username"],
        display_name=row["display_name"],
        password_hash=row["password_hash"],
        status=row["status"],
        is_admin=row["is_admin"],
    )


def _row_to_pending_record(row: asyncpg.Record) -> PendingUserRecord:
    return PendingUserRecord(
        id=str(row["id"]),
        username=row["username"],
        display_name=row["display_name"],
        status=row["status"],
        created_at=row["created_at"],
    )
