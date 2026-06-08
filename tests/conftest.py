"""根conftest — 全局统一的环境清理与测试常量

两级autouse fixture：
1. session级：注入测试必需环境变量（JWT密钥、测试DB名），确保直接pytest也能运行
2. function级：env snapshot/restore（兜底monkeypatch泄漏）+ DB TRUNCATE（仅集成/基准测试）+ app.state清空

测试常量集中定义于此，不在正式代码中放置测试专用值。
"""

import os

import pytest


# 测试专用常量——>=32 bytes，消除PyJWT InsecureKeyLengthWarning
JWT_SECRET_TEST = "orbion-test-secret-key-at-least-32-by"

_ENV_PREFIX = "ORBION_"

# 测试必需环境变量——session级注入，不依赖Makefile
_TEST_ENV_VARS = {
    "ORBION_JWT_SECRET": JWT_SECRET_TEST,
    "ORBION_POSTGRES__DB": "orbion_test",
}

# 懒初始化表名缓存——首次TRUNCATE时查询pg_tables并缓存，后续直接使用。
# 局限：单次pytest session内schema不变时有效；若中途ALTER TABLE增删列，需重启pytest。
_DB_TABLES_CACHE: str | None = None


async def _truncate_all_tables(db_url: str) -> None:
    """动态发现public schema下所有用户表并TRUNCATE CASCADE

    Why: 硬编码表名列表需要手动维护，增删表后容易遗漏导致测试间数据残留。
    查询pg_tables动态发现所有业务表，一次TRUNCATE全部清空。
    表名只在第一次调用时查询并缓存（全局变量），后续直接使用缓存值。
    每次TRUNCATE使用新建连接（避免pytest-asyncio跨event loop问题）。
    """
    import asyncpg

    global _DB_TABLES_CACHE
    conn = await asyncpg.connect(db_url)
    if _DB_TABLES_CACHE is None:
        rows = await conn.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        )
        _DB_TABLES_CACHE = ", ".join(r["tablename"] for r in rows)
    await conn.execute(f"TRUNCATE {_DB_TABLES_CACHE} CASCADE")
    await conn.close()


def _clear_app_state() -> None:
    """遍历删除app.state上的全部属性，不留任何残留

    Why: 硬编码属性名列表需要手动维护，增删service后容易遗漏。
    直接遍历app.state上所有属性逐个删除，彻底清空。
    """
    from app.main import app

    for attr in list(app.state._state.keys()):
        delattr(app.state, attr)


@pytest.fixture(autouse=True, scope="session")
def _inject_test_env_vars() -> None:
    """注入测试必需环境变量，确保直接pytest也能运行（不依赖Makefile）

    Why: jwt_secret无默认值，直接pytest时缺少ORBION_JWT_SECRET会ValidationError。
    session级注入一次，session结束时恢复原始环境。
    """
    saved = {}
    for key, value in _TEST_ENV_VARS.items():
        saved[key] = os.environ.get(key)
        os.environ[key] = value
    yield
    for key, orig in saved.items():
        if orig is None:
            del os.environ[key]
        else:
            os.environ[key] = orig


@pytest.fixture(autouse=True, scope="function")
async def _clean_env(request: pytest.FixtureRequest) -> None:
    """每个测试前后统一清理：env vars + DB + app.state

    setup: env snapshot → DB TRUNCATE (仅集成/基准测试，缓存表名避免重复查询)
    teardown: env restore → app.state清空
    """
    # -- setup: env snapshot --
    env_snapshot = {k: v for k, v in os.environ.items() if k.startswith(_ENV_PREFIX)}

    # -- setup: DB TRUNCATE (仅集成/基准测试，单元测试不碰DB) --
    is_unit_test = "tests/unit" in str(request.path)
    if not is_unit_test:
        try:
            from app.config import get_settings
            import asyncpg

            await _truncate_all_tables(get_settings().postgres.url)
        except (OSError, asyncpg.PostgresConnectionError):
            # DB不可用时自动skip，不阻止单元测试运行
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