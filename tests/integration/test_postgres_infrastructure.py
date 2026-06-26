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
    """执行migrations/下全部脚本，验证表和所有索引+约束创建成功（含 AR-1.1 Agent Runtime 新表）"""
    settings = get_settings()
    conn = await asyncpg.connect(settings.postgres.url)
    try:
        await conn.execute(
            "DROP TABLE IF EXISTS dead_letter_events, outbox_events, skill_calls, "
            "model_usage_archive, model_usage_daily, model_usage_details, "
            "agent_runs, tasks, artifacts, user_models, "
            "worktrees, task_outputs, execution_plans, thread_messages, "
            "threads, project_members, projects, users, event_log CASCADE"
        )

        # 按文件名顺序执行全部迁移脚本
        import glob

        migration_files = sorted(glob.glob("migrations/*.sql"))
        assert migration_files, "未找到迁移脚本"
        for sql_file in migration_files:
            with open(sql_file) as f:
                migration_sql = f.read()
            await conn.execute(migration_sql)

        tables = await conn.fetch("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        table_names = {row["tablename"] for row in tables}
        expected_tables = {
            # MVP 原表
            "event_log",
            "users",
            "projects",
            "project_members",
            "threads",
            "thread_messages",
            "execution_plans",
            "task_outputs",
            "worktrees",
            # Agent Runtime 新表（AR-1.1）
            "user_models",
            "artifacts",
            "tasks",
            "agent_runs",
            "model_usage_details",
            "model_usage_daily",
            "model_usage_archive",
            "skill_calls",
            "outbox_events",
            "dead_letter_events",
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
            "idx_worktrees_project_type",
            "idx_worktrees_task",
            "uq_worktrees_active_branch",
            "uq_worktrees_active_task",
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

        # 验证 worktrees 表字段齐全（GW-1.1）
        wt_columns = await conn.fetch(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'worktrees'"
        )
        wt_column_names = {row["column_name"] for row in wt_columns}
        expected_wt_columns = {
            "id",
            "project_id",
            "repo_name",
            "worktree_type",
            "branch_name",
            "path",
            "status",
            "created_by",
            "task_id",
            "created_at",
            "updated_at",
        }
        assert expected_wt_columns <= wt_column_names, f"缺少 worktrees 字段: {expected_wt_columns - wt_column_names}"

        # 验证 worktrees CHECK 约束
        wt_checks = await conn.fetch(
            "SELECT pg_get_constraintdef(oid) AS def FROM pg_constraint "
            "WHERE conrelid = 'worktrees'::regclass AND contype = 'c'"
        )
        wt_check_defs = {row["def"] for row in wt_checks}
        assert any("worktree_type" in c and "main" in c for c in wt_check_defs), "缺少 worktree_type CHECK"
        assert any("status" in c and "active" in c for c in wt_check_defs), "缺少 status CHECK"

        # === AR-1.1 Agent Runtime 新表字段验证 ===
        # user_models 表
        um_columns = await conn.fetch(
            "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'user_models'"
        )
        um_col_map = {row["column_name"]: row["data_type"] for row in um_columns}
        assert "api_key_enc" in um_col_map, "缺少 user_models.api_key_enc"
        assert um_col_map["api_key_enc"] == "bytea", f"api_key_enc 应为 bytea，实际 {um_col_map['api_key_enc']}"
        assert "api_key_hash" in um_col_map, "缺少 user_models.api_key_hash"
        assert "user_id" in um_col_map and "model_id" in um_col_map, "缺少 user_models 主键字段"

        # user_models (user_id, model_id) 唯一键
        um_constraints = await conn.fetch(
            "SELECT conname FROM pg_constraint WHERE conrelid = 'user_models'::regclass AND contype = 'u'"
        )
        um_unique_names = {row["conname"] for row in um_constraints}
        assert len(um_unique_names) > 0, "user_models 缺少唯一约束"

        # artifacts 表关键字段
        art_columns = await conn.fetch(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'artifacts'"
        )
        art_col_names = {row["column_name"] for row in art_columns}
        for col in ["based_on_artifacts", "status_changed_at", "last_reminded_at"]:
            assert col in art_col_names, f"缺少 artifacts.{col}"

        # artifacts based_on_artifacts 为 JSONB
        art_based_on_type = await conn.fetchval(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_name = 'artifacts' AND column_name = 'based_on_artifacts'"
        )
        assert art_based_on_type == "jsonb", f"artifacts.based_on_artifacts 应为 jsonb，实际 {art_based_on_type}"

        # artifacts GIN 索引存在
        art_indexes = await conn.fetch("SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'artifacts'")
        assert any("GIN" in row["indexdef"].upper() for row in art_indexes), "artifacts 缺少 GIN 索引"

        # tasks 表 6 状态 CHECK
        task_checks = await conn.fetch(
            "SELECT pg_get_constraintdef(oid) AS def FROM pg_constraint "
            "WHERE conrelid = 'tasks'::regclass AND contype = 'c'"
        )
        task_check_defs = {row["def"] for row in task_checks}
        assert any("status" in c and "pending" in c and "running" in c for c in task_check_defs), (
            "缺少 tasks.status CHECK"
        )

        # tasks 关键字段
        task_columns = await conn.fetch("SELECT column_name FROM information_schema.columns WHERE table_name = 'tasks'")
        task_col_names = {row["column_name"] for row in task_columns}
        for col in ["based_on_artifacts", "based_on_tasks", "revision_count", "conflict_regen_count"]:
            assert col in task_col_names, f"缺少 tasks.{col}"

        # agent_runs 表 5 状态 + 关键字段
        ar_columns = await conn.fetch(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'agent_runs'"
        )
        ar_col_names = {row["column_name"] for row in ar_columns}
        for col in ["status", "cancel_reason", "trace_id", "event_id", "task_id", "agent_type", "run_kind"]:
            assert col in ar_col_names, f"缺少 agent_runs.{col}"

        # agent_runs 5 状态 CHECK
        ar_checks = await conn.fetch(
            "SELECT pg_get_constraintdef(oid) AS def FROM pg_constraint "
            "WHERE conrelid = 'agent_runs'::regclass AND contype = 'c'"
        )
        ar_check_defs = {row["def"] for row in ar_checks}
        assert any("running" in c and "completed" in c and "interrupted" in c for c in ar_check_defs), (
            "缺少 agent_runs.status CHECK"
        )

        # agent_runs (event_id, agent_type) 幂等唯一键（部分唯一索引，查 pg_indexes）
        ar_indexes = await conn.fetch("SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'agent_runs'")
        ar_index_defs = {row["indexname"]: row["indexdef"] for row in ar_indexes}
        assert "agent_runs_event_agent_unique" in ar_index_defs, "缺少 (event_id, agent_type) 幂等唯一索引"
        assert (
            "event_id" in ar_index_defs["agent_runs_event_agent_unique"]
            and "agent_type" in ar_index_defs["agent_runs_event_agent_unique"]
        ), "幂等索引应含 event_id + agent_type"

        # agent_runs 部分唯一索引 agent_runs_task_running_idx
        ar_indexes = await conn.fetch("SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'agent_runs'")
        ar_index_defs = {row["indexname"]: row["indexdef"] for row in ar_indexes}
        assert "agent_runs_task_running_idx" in ar_index_defs, "缺少 agent_runs_task_running_idx 部分唯一索引"
        assert "WHERE" in ar_index_defs["agent_runs_task_running_idx"].upper(), (
            "agent_runs_task_running_idx 应为部分索引"
        )
        assert "running" in ar_index_defs["agent_runs_task_running_idx"], (
            "agent_runs_task_running_idx 应 WHERE status='running'"
        )

        # model_usage_details / daily / archive 三表
        for tbl in ["model_usage_details", "model_usage_daily", "model_usage_archive"]:
            tbl_exists = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM pg_tables WHERE schemaname='public' AND tablename=$1)", tbl
            )
            assert tbl_exists, f"缺少表 {tbl}"

        # model_usage_daily 联合唯一键 (user_id, model_id, agent_type, date)
        mud_unique = await conn.fetch(
            "SELECT pg_get_constraintdef(oid) AS def FROM pg_constraint "
            "WHERE conrelid = 'model_usage_daily'::regclass AND contype = 'u'"
        )
        mud_unique_defs = {row["def"] for row in mud_unique}
        assert any("user_id" in c and "model_id" in c and "agent_type" in c and "date" in c for c in mud_unique_defs), (
            "缺少 model_usage_daily 联合唯一键"
        )

        # model_usage_archive 联合唯一键 (user_id, date)
        mua_unique = await conn.fetch(
            "SELECT pg_get_constraintdef(oid) AS def FROM pg_constraint "
            "WHERE conrelid = 'model_usage_archive'::regclass AND contype = 'u'"
        )
        mua_unique_defs = {row["def"] for row in mua_unique}
        assert any("user_id" in c and "date" in c for c in mua_unique_defs), "缺少 model_usage_archive 联合唯一键"

        # skill_calls / outbox_events / dead_letter_events 表存在
        for tbl in ["skill_calls", "outbox_events", "dead_letter_events"]:
            tbl_exists = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM pg_tables WHERE schemaname='public' AND tablename=$1)", tbl
            )
            assert tbl_exists, f"缺少表 {tbl}"

        # outbox_events 退避查询关键字段 + 索引（§9.3 退避策略依赖）
        outbox_cols = await conn.fetch(
            "SELECT column_name FROM information_schema.columns WHERE table_name='outbox_events'"
        )
        outbox_col_names = {row["column_name"] for row in outbox_cols}
        for col in ["next_retry_at", "retry_count", "processed_at", "status"]:
            assert col in outbox_col_names, f"缺少 outbox_events.{col}"
        outbox_indexes = await conn.fetch("SELECT indexname FROM pg_indexes WHERE tablename='outbox_events'")
        outbox_index_names = {row["indexname"] for row in outbox_indexes}
        assert "idx_outbox_events_status_retry" in outbox_index_names, "缺少 outbox_events 退避查询索引"

        # === AR-1.7 event_log.payload_ref_url 字段 ===
        el_columns = await conn.fetch(
            "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
            "WHERE table_name = 'event_log' AND column_name = 'payload_ref_url'"
        )
        assert len(el_columns) == 1, "缺少 event_log.payload_ref_url 字段"
        assert el_columns[0]["data_type"] == "character varying", (
            f"payload_ref_url 应为 VARCHAR，实际 {el_columns[0]['data_type']}"
        )
        assert el_columns[0]["is_nullable"] == "YES", "payload_ref_url 应可为 NULL"
    finally:
        await conn.close()
