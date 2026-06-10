"""PostgreSQL基础设施验证：连接 + migration"""

import asyncpg

from app.config import get_settings


async def test_postgres_connection() -> None:
    """asyncpg连接 postgres.url，SELECT 1成功"""
    settings = get_settings()
    conn = await asyncpg.connect(settings.postgres.url)
    try:
        result = await conn.fetchval("SELECT 1")
        assert result == 1
    finally:
        await conn.close()


async def test_postgres_migration_creates_tables_and_indexes() -> None:
    """执行migrations/001，验证8张表和所有索引+约束创建成功"""
    settings = get_settings()
    conn = await asyncpg.connect(settings.postgres.url)
    try:
        await conn.execute(
            "DROP TABLE IF EXISTS task_outputs, execution_plans, thread_messages, "
            "threads, project_members, projects, users, event_log CASCADE"
        )

        with open("migrations/001_initial.sql") as f:
            migration_sql = f.read()
        await conn.execute(migration_sql)

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

        # 验证唯一约束
        constraints = await conn.fetch(
            "SELECT conname FROM pg_constraint WHERE conrelid = 'projects'::regclass OR conrelid = 'threads'::regclass"
        )
        constraint_names = {row["conname"] for row in constraints}
        assert "projects_name_unique" in constraint_names
        assert "threads_project_title_unique" in constraint_names

        # 验证projects有default_thread_id列
        columns = await conn.fetch("SELECT column_name FROM information_schema.columns WHERE table_name = 'projects'")
        column_names = {row["column_name"] for row in columns}
        assert "default_thread_id" in column_names
    finally:
        await conn.close()
