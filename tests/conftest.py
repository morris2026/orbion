"""根conftest — 全局统一的环境清理与测试常量

单一autouse fixture覆盖三个维度：
1. 环境变量：setup snapshot + teardown restore（兜底monkeypatch泄漏）
2. 数据库：setup 动态发现业务表并TRUNCATE CASCADE（DB不可用时自动skip）
3. app.state：teardown 遍历删除全部属性（兜底fixture残留）

测试常量集中定义于此，不在正式代码中放置测试专用值。
"""

import os

import pytest


# 测试专用常量——>=32 bytes，消除PyJWT InsecureKeyLengthWarning
JWT_SECRET_TEST = "orbion-test-secret-key-at-least-32-by"

_ENV_PREFIX = "ORBION_"


async def _truncate_all_tables(db_url: str) -> None:
    """动态发现public schema下所有用户表并TRUNCATE CASCADE

    Why: 硬编码表名列表需要手动维护，增删表后容易遗漏导致测试间数据残留。
    查询pg_tables动态发现所有业务表，一次TRUNCATE全部清空。
    """
    import asyncpg

    conn = await asyncpg.connect(db_url)
    rows = await conn.fetch(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
    )
    tables = [r["tablename"] for r in rows]
    if tables:
        await conn.execute(f"TRUNCATE {', '.join(tables)} CASCADE")
    await conn.close()


def _clear_app_state() -> None:
    """遍历删除app.state上的全部属性，不留任何残留

    Why: 硬编码属性名列表需要手动维护，增删service后容易遗漏。
    直接遍历app.state上所有属性逐个删除，彻底清空。
    """
    from app.main import app

    # State内部用dict存储，遍历其所有key逐个删除
    for attr in list(app.state._state.keys()):
        delattr(app.state, attr)


@pytest.fixture(autouse=True, scope="function")
async def _clean_env() -> None:
    """每个测试前后统一清理：env vars + DB + app.state

    setup: snapshot env vars → 动态TRUNCATE DB (skip if unavailable)
    teardown: restore env vars → 清空app.state全部属性
    """
    # -- setup: env snapshot --
    env_snapshot = {k: v for k, v in os.environ.items() if k.startswith(_ENV_PREFIX)}

    # -- setup: DB TRUNCATE (skip if PostgreSQL不可连接) --
    try:
        from app.config import get_settings

        await _truncate_all_tables(get_settings().postgres.url)
    except (OSError, Exception):
        pass

    yield

    # -- teardown: env restore (兜底monkeypatch泄漏) --
    for key in list(os.environ):
        if key.startswith(_ENV_PREFIX) and key not in env_snapshot:
            del os.environ[key]
    for key, value in env_snapshot.items():
        os.environ[key] = value

    # -- teardown: app.state 清空 (兜底fixture残留) --
    _clear_app_state()