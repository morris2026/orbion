"""共享session级fixture — Docker PG启停与数据库迁移"""

import subprocess
import time
from collections.abc import Generator
from pathlib import Path

import asyncpg
import pytest

from app.config import get_settings

settings = get_settings()
MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def _wait_for_postgres() -> None:
    """轮询等待PG就绪"""
    import asyncio

    async def _try() -> None:
        conn = await asyncpg.connect(settings.postgres.url)
        await conn.close()

    for _ in range(30):
        try:
            asyncio.run(_try())
            return
        except Exception:
            time.sleep(1)
    raise RuntimeError("PostgreSQL未在30秒内就绪")


async def _run_migrations() -> None:
    """清空现有表后执行所有迁移SQL"""
    conn = await asyncpg.connect(settings.postgres.url)
    tables = await conn.fetch("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    for t in tables:
        await conn.execute(f"DROP TABLE IF EXISTS {t['tablename']} CASCADE")
    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    for mf in migration_files:
        await conn.execute(mf.read_text())
    await conn.close()


@pytest.fixture(scope="session", autouse=True)
def _docker_postgres() -> Generator[None, None, None]:
    """集成/基准测试 session 级自动启停 Docker PostgreSQL + 执行数据库迁移"""
    subprocess.run(["docker", "compose", "up", "-d", "postgres"], check=True)
    _wait_for_postgres()
    import asyncio

    asyncio.run(_run_migrations())
    yield
    subprocess.run(["docker", "compose", "down"], check=True)
