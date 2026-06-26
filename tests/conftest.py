"""根conftest — 全局统一的环境清理与测试常量

两级autouse fixture：
1. session级：注入测试必需环境变量（JWT密钥、测试DB名），确保直接pytest也能运行
2. function级：env snapshot/restore（兜底monkeypatch泄漏）+ DB TRUNCATE（仅集成/基准测试）+ app.state清空

测试常量集中定义于此，不在正式代码中放置测试专用值。
"""

import asyncio
import glob
import os
from collections.abc import AsyncGenerator, Generator

import asyncpg
import pytest

# 测试专用常量——>=32 bytes，消除PyJWT InsecureKeyLengthWarning
JWT_SECRET_TEST = "orbion-test-secret-key-at-least-32-by"

_ENV_PREFIX = "ORBION_"


def _ensure_worker_db(db_name: str) -> None:
    """xdist worker 启动时创建独立 DB + 应用全部迁移（同步包装 asyncpg）

    Why: 并行测试时多个 worker 共享同一 DB 会 TRUNCATE 互相干扰，
    每个 worker 用 orbion_test_gw{N} 独立 DB 隔离。
    """
    from app.config import get_settings

    settings = get_settings()

    async def _setup() -> None:
        # 连接 postgres 管理库创建 DB
        admin_url = (
            f"postgresql://{settings.postgres.user}:{settings.postgres.password}"
            f"@{settings.postgres.host}:{settings.postgres.port}/postgres"
        )
        conn = await asyncpg.connect(admin_url)
        try:
            exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname=$1", db_name)
            if exists:
                # 终止所有连接后 DROP，保证干净重建
                await conn.execute(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=$1",
                    db_name,
                )
                await conn.execute(f'DROP DATABASE "{db_name}"')
            await conn.execute(f'CREATE DATABASE "{db_name}"')
        finally:
            await conn.close()

        # 应用全部迁移
        db_url = (
            f"postgresql://{settings.postgres.user}:{settings.postgres.password}"
            f"@{settings.postgres.host}:{settings.postgres.port}/{db_name}"
        )
        conn = await asyncpg.connect(db_url)
        try:
            for sql_file in sorted(glob.glob("migrations/*.sql")):
                with open(sql_file) as f:
                    await conn.execute(f.read())
        finally:
            await conn.close()

    asyncio.run(_setup())


# 测试必需环境变量——session级注入，不依赖Makefile
_TEST_ENV_VARS = {
    "ORBION_JWT_SECRET": JWT_SECRET_TEST,
    "ORBION_POSTGRES__DB": "orbion_test",
    # AES-256-GCM 加密密钥（32 字节 base64），用于 user_models.api_key_enc + agent_models.enc
    "ORBION_ENCRYPTION_KEY": "YWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWE=",
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
        rows = await conn.fetch("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
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
def _inject_test_env_vars(request: pytest.FixtureRequest) -> Generator[None, None, None]:
    """注入测试必需环境变量，确保直接pytest也能运行（不依赖Makefile）

    Why: jwt_secret无默认值，直接pytest时缺少ORBION_JWT_SECRET会ValidationError。
    session级注入一次，session结束时恢复原始环境。

    xdist: 每个 worker 用独立 DB（orbion_test_gw0/gw1/...），避免并行 TRUNCATE 互相干扰。
    """
    # 先注入全部测试环境变量
    saved = {}
    for key, value in _TEST_ENV_VARS.items():
        saved[key] = os.environ.get(key)
        os.environ[key] = value

    # xdist worker 独立 DB（覆盖默认 orbion_test）
    worker_id = getattr(request.config, "workerinput", {}).get("workerid", "master")
    if worker_id != "master":
        db_name = f"orbion_test_{worker_id}"
        os.environ["ORBION_POSTGRES__DB"] = db_name
        _ensure_worker_db(db_name)
    yield
    for key, orig in saved.items():
        if orig is None:
            del os.environ[key]
        else:
            os.environ[key] = orig


@pytest.fixture(autouse=True, scope="function")
async def _clean_env(request: pytest.FixtureRequest) -> AsyncGenerator[None, None]:
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
            import asyncpg

            from app.config import get_settings

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
