"""步骤7 UserRepository抽象层UT：Protocol conformance、domain models、生命周期边界"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.hub.auth.postgres_repo import PostgresUserRepository
from app.hub.auth.repository import (
    PendingUserRecord,
    UserRecord,
    UserRepositoryProtocol,
    load_user_repo_impl,
)


class TestUserRecordModels:
    """domain models验证"""

    def test_user_record_all_fields(self) -> None:
        """UserRecord完整字段"""
        record = UserRecord(
            id="user-1",
            username="admin",
            display_name="Admin",
            password_hash="$2b$...",
            status="active",
            is_admin=True,
        )
        assert record.id == "user-1"
        assert record.username == "admin"
        assert record.is_admin is True

    def test_user_record_default_is_admin(self) -> None:
        """is_admin默认False"""
        record = UserRecord(id="user-2", username="viewer", display_name="Viewer", password_hash="x", status="pending")
        assert record.is_admin is False

    def test_pending_user_record(self) -> None:
        """PendingUserRecord字段"""
        record = PendingUserRecord(
            id="user-3", username="pending1", display_name="P1", status="pending", created_at=datetime.now()
        )
        assert record.status == "pending"
        assert record.created_at is not None

    def test_pending_user_record_created_at_required(self) -> None:
        """created_at必填，缺失抛ValidationError"""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            PendingUserRecord(id="user-4", username="p2", display_name="P2", status="pending")  # type: ignore[call-arg]


class TestUserRepositoryProtocolConformance:
    """Protocol conformance验证"""

    def test_postgres_impl_satisfies_protocol(self) -> None:
        """PostgresUserRepository继承UserRepositoryProtocol"""
        cls = load_user_repo_impl("postgres")
        assert issubclass(cls, UserRepositoryProtocol)

    def test_load_unknown_impl_raises_value_error(self) -> None:
        """未注册实现名抛ValueError"""
        with pytest.raises(ValueError, match="未注册"):
            load_user_repo_impl("unknown")


class TestPostgresUserRepositoryLifecycle:
    """PostgresUserRepository生命周期边界测试"""

    def test_ensure_open_raises_before_enter(self) -> None:
        """CRUD方法在未进入context manager时抛RuntimeError"""
        pool = MagicMock()
        repo = PostgresUserRepository(pool)
        with pytest.raises(RuntimeError, match="未进入"):
            repo._ensure_open()

    @pytest.mark.asyncio
    async def test_ensure_open_raises_after_exit(self) -> None:
        """CRUD方法在退出context manager后抛RuntimeError"""
        mock_conn = AsyncMock()
        mock_tx = AsyncMock()
        # conn.transaction()是同步方法（返回Transaction对象），用MagicMock模拟
        mock_conn.transaction = MagicMock(return_value=mock_tx)

        pool = AsyncMock()
        pool.acquire.return_value = mock_conn
        pool.release = AsyncMock()

        repo = PostgresUserRepository(pool)
        async with repo:
            pass
        with pytest.raises(RuntimeError, match="已退出"):
            repo._ensure_open()

    @pytest.mark.asyncio
    async def test_aexit_resets_conn_and_tx(self) -> None:
        """__aexit__后_conn和_tx重置为None"""
        mock_conn = AsyncMock()
        mock_tx = AsyncMock()
        mock_conn.transaction = MagicMock(return_value=mock_tx)

        pool = AsyncMock()
        pool.acquire.return_value = mock_conn
        pool.release = AsyncMock()

        repo = PostgresUserRepository(pool)
        async with repo:
            pass
        assert repo._conn is None
        assert repo._tx is None
