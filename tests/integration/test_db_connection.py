"""TC-1.4：PostgreSQL连接集成测试"""

import asyncpg
import pytest

from app.config import Settings


@pytest.mark.asyncio
async def test_tc1_4_postgres_connection() -> None:
    """TC-1.4：docker compose up后，用asyncpg连接postgres_url，SELECT 1成功"""
    settings = Settings()
    conn = await asyncpg.connect(settings.postgres_url)
    try:
        result = await conn.fetchval("SELECT 1")
        assert result == 1
    finally:
        await conn.close()
