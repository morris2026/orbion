"""TC-2.1：数据库迁移执行集成测试"""

import asyncpg
import pytest

from app.config import Settings


@pytest.mark.asyncio
async def test_tc2_1_migration_creates_tables_and_indexes() -> None:
    """TC-2.1：执行migrations/001_initial.sql，验证8张表和所有索引创建成功"""
    settings = Settings()
    conn = await asyncpg.connect(settings.postgres_url)
    try:
        # 清理已有表，确保迁移在干净数据库上执行
        await conn.execute(
            "DROP TABLE IF EXISTS task_outputs, execution_plans, thread_messages, "
            "threads, project_members, projects, users, event_log CASCADE"
        )

        # 读取迁移文件并执行
        with open("migrations/001_initial.sql") as f:
            migration_sql = f.read()
        await conn.execute(migration_sql)

        # 验证8张表全部创建成功
        tables = await conn.fetch("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        table_names = {row["tablename"] for row in tables}
        expected_tables = {
            "event_log",
            "users",
            "projects",
            "project_members",
            "threads",
            "thread_messages",
            "execution_plans",
            "task_outputs",
        }
        assert expected_tables <= table_names, f"缺少表: {expected_tables - table_names}"

        # 验证所有索引创建成功
        indexes = await conn.fetch("SELECT indexname FROM pg_indexes WHERE schemaname = 'public'")
        index_names = {row["indexname"] for row in indexes}
        expected_indexes = {
            "idx_event_log_project",
            "idx_event_log_correlation",
            "idx_event_log_type",
            "idx_project_members_project",
            "idx_project_members_agent",
            "idx_threads_project",
            "idx_thread_messages_thread",
            "idx_thread_messages_summary",
            "idx_execution_plans_project",
            "idx_execution_plans_thread",
            "idx_execution_plans_status",
            "idx_task_outputs_project",
            "idx_task_outputs_status",
        }
        assert expected_indexes <= index_names, f"缺少索引: {expected_indexes - index_names}"
    finally:
        await conn.close()
