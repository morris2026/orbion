"""PostgreSQL测试基础设施：Docker启停 + 数据库迁移 + 共享fixture"""

import subprocess
import time
from collections.abc import AsyncGenerator, Generator
from pathlib import Path

import asyncpg
import pytest

from app.config import get_settings

settings = get_settings()
MIGRATIONS_DIR = Path(__file__).resolve().parent.parent.parent / "migrations"

# 所有业务表，按外键依赖顺序（子表先删）
CLEAN_TABLES = [
    "task_outputs",
    "execution_plans",
    "thread_messages",
    "project_members",
    "threads",
    "projects",
    "event_log",
    "users",
]


def _wait_for_postgres() -> None:
    """用 asyncpg 轮询等待 PostgreSQL 就绪"""
    import asyncio

    async def _try_connect() -> None:
        conn = await asyncpg.connect(settings.postgres.url)
        await conn.close()

    for _ in range(30):
        try:
            asyncio.run(_try_connect())
            return
        except Exception:
            time.sleep(1)
    raise RuntimeError("PostgreSQL did not become ready within 30 seconds")


async def _run_migrations() -> None:
    """清空现有表后执行所有迁移SQL文件（确保schema一致性）"""
    conn = await asyncpg.connect(settings.postgres.url)
    # 清空现有表（测试每次从干净schema开始）
    tables = await conn.fetch("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    for t in tables:
        await conn.execute(f"DROP TABLE IF EXISTS {t['tablename']} CASCADE")
    # 按文件名排序执行迁移
    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    for mf in migration_files:
        await conn.execute(mf.read_text())
    await conn.close()


@pytest.fixture(scope="session", autouse=True)
def _docker_postgres() -> Generator[None, None, None]:
    """集成测试 session 级自动启停 Docker PostgreSQL + 执行数据库迁移"""
    subprocess.run(["docker", "compose", "up", "-d", "postgres"], check=True)
    _wait_for_postgres()
    import asyncio

    asyncio.run(_run_migrations())
    yield
    subprocess.run(["docker", "compose", "down"], check=True)


@pytest.fixture
async def postgres_pool() -> AsyncGenerator[asyncpg.Pool, None]:
    """PostgreSQL连接池（临时：seeding/cleanup绕过抽象层直接操作DB）"""
    pool = await asyncpg.create_pool(get_settings().postgres.url, min_size=1, max_size=5)
    yield pool
    await pool.close()


@pytest.fixture
async def db_conn() -> AsyncGenerator[asyncpg.Connection, None]:
    """共享DB连接fixture：测试前后清空所有业务表"""
    conn = await asyncpg.connect(settings.postgres.url)
    for table in CLEAN_TABLES:
        await conn.execute(f"DELETE FROM {table}")
    yield conn
    for table in CLEAN_TABLES:
        await conn.execute(f"DELETE FROM {table}")
    await conn.close()


@pytest.fixture(autouse=True, scope="function")
async def _clean_test_tables() -> None:
    """自动清理所有业务表，确保每个测试从干净数据库开始
    Why: db_conn fixture非autouse，18/24个集成测试不请求它，
    导致数据库状态在测试间累积→username UNIQUE约束冲突→间歇性失败
    """
    conn = await asyncpg.connect(settings.postgres.url)
    for table in CLEAN_TABLES:
        await conn.execute(f"DELETE FROM {table}")
    await conn.close()
