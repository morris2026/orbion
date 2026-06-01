"""PostgreSQL测试seeding临时方案

当前MVP没有ProjectCreated/ThreadCreated等领域事件，投影测试需要的前置数据
（projects、threads表行）只能通过直接DB INSERT实现。本文件提供独立连接池
用于seeding和cleanup，绕过抽象层直接操作数据库。

⚠️ 这是临时方案，后续替换目标：
- 补充ProjectCreated/ThreadCreated等领域事件类型
- 投影处理器订阅这些事件，自动写入projects/threads表
- 测试seeding改为通过EventStore.append + EventBus.publish发送领域事件
- 删除本文件，seeding逻辑回归test_projections.py通过事件通道完成
"""

import subprocess
import time
from collections.abc import AsyncGenerator, Generator

import asyncpg
import pytest

from app.config import get_settings

settings = get_settings()


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


@pytest.fixture(scope="session", autouse=True)
def _docker_postgres() -> Generator[None, None, None]:
    """集成测试 session 级自动启停 Docker PostgreSQL"""
    subprocess.run(["docker", "compose", "up", "-d", "postgres"], check=True)
    _wait_for_postgres()
    yield
    subprocess.run(["docker", "compose", "down"], check=True)


@pytest.fixture
async def postgres_pool() -> AsyncGenerator[asyncpg.Pool, None]:
    """PostgreSQL连接池（临时：seeding/cleanup绕过抽象层直接操作DB）"""
    pool = await asyncpg.create_pool(get_settings().postgres.url, min_size=1, max_size=5)
    yield pool
    await pool.close()
