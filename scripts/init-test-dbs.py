"""Idempotent 测试数据库初始化：创建 orbion_test/orbion_e2e + 在所有数据库上执行 migration

Why: 开发者已有 pgdata volume 时，docker-entrypoint-initdb.d 不会重新执行，
需要手动运行此脚本补充测试数据库。新开发者不需要此脚本——PG 首次启动自动初始化。
"""

import asyncio
import sys
from pathlib import Path

import asyncpg

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
PG_HOST = "localhost"
PG_PORT = 5432
PG_USER = "orbion"
PG_PASSWORD = "orbion_dev"
PG_DEFAULT_DB = "orbion"
TEST_DATABASES = ["orbion_test", "orbion_e2e"]


async def init() -> None:
    # 连接默认数据库（orbion 用户有 CREATE DATABASE 权限）
    conn = await asyncpg.connect(
        host=PG_HOST, port=PG_PORT, user=PG_USER, password=PG_PASSWORD, database=PG_DEFAULT_DB
    )

    # 创建测试数据库（idempotent：已存在时跳过）
    existing = {r["datname"] for r in await conn.fetch("SELECT datname FROM pg_database")}
    for db_name in TEST_DATABASES:
        if db_name not in existing:
            await conn.execute(f'CREATE DATABASE "{db_name}"')
            print(f"创建数据库 {db_name}")
        else:
            print(f"数据库 {db_name} 已存在，跳过")

    await conn.close()

    # 在所有数据库上执行 migration（idempotent：先 DROP 再 CREATE）
    migration_sql = sorted(MIGRATIONS_DIR.glob("*.sql"))
    for db_name in [PG_DEFAULT_DB] + TEST_DATABASES:
        db_conn = await asyncpg.connect(
            host=PG_HOST, port=PG_PORT, user=PG_USER, password=PG_PASSWORD, database=db_name
        )
        # 先删除所有表（按 FK 依赖从叶子到根），确保可重复执行
        tables = await db_conn.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        )
        for t in tables:
            await db_conn.execute(f'DROP TABLE IF EXISTS {t["tablename"]} CASCADE')
        # 执行 migration SQL
        for mf in migration_sql:
            await db_conn.execute(mf.read_text())
        print(f"数据库 {db_name} migration 完成（{len(migration_sql)} 个文件）")
        await db_conn.close()

    print("==> 初始化完成")


if __name__ == "__main__":
    asyncio.run(init())