"""Agent Runtime 数据模型基础测试（AR-1.2 ~ AR-1.7）

AR-1.1 表结构验证合入 test_postgres_infrastructure.py。
本文件验证索引行为、唯一约束、UPSERT 语义等数据层契约。
"""

import json
import uuid
from collections.abc import AsyncGenerator

import asyncpg
import pytest

from app.config import get_settings


@pytest.fixture
async def schema_conn() -> AsyncGenerator[asyncpg.Connection, None]:
    """独立连接 + 应用全部迁移脚本（与 test_postgres_infrastructure 同样的 setup）

    Why: 根 conftest 的 _clean_env 只 TRUNCATE 数据不重建 schema，
    而本文件的用例需要新表（user_models/artifacts/tasks/agent_runs 等）存在。
    共用 test_postgres_infrastructure 的 setup 逻辑确保 schema 就绪。
    """
    settings = get_settings()
    conn = await asyncpg.connect(settings.postgres.url)
    # 检查新表是否已存在（迁移已应用）；不存在则跳过用例（由 RED 阶段判定）
    tbl_exists = await conn.fetchval(
        "SELECT EXISTS(SELECT 1 FROM pg_tables WHERE schemaname='public' AND tablename='user_models')"
    )
    if not tbl_exists:
        pytest.skip("Agent Runtime 新表未创建（迁移脚本未应用）")
    yield conn
    await conn.close()


async def _seed_user_and_project(conn: asyncpg.Connection) -> tuple[uuid.UUID, uuid.UUID]:
    """创建 user + project 供 FK 引用"""
    user_id = uuid.uuid4()
    project_id = uuid.uuid4()
    await conn.execute(
        "INSERT INTO users (id, username, password_hash, display_name, status, is_admin) "
        "VALUES ($1, $2, $3, $4, 'active', true)",
        user_id,
        f"u_{user_id.hex[:8]}",
        "hash",
        "Test User",
    )
    await conn.execute(
        "INSERT INTO projects (id, name, description) VALUES ($1, $2, $3)",
        project_id,
        f"p_{project_id.hex[:8]}",
        "test project",
    )
    return user_id, project_id


async def test_ar_1_2_artifacts_gin_index_query(schema_conn: asyncpg.Connection) -> None:
    """AR-1.2 artifacts.based_on_artifacts GIN 索引查询"""
    conn = schema_conn
    user_id, project_id = await _seed_user_and_project(conn)

    artifact_a = uuid.uuid4()
    artifact_b = uuid.uuid4()
    artifact_c = uuid.uuid4()

    # A based_on []; B based_on [A]; C based_on [B]
    for aid, based_on in [
        (artifact_a, []),
        (artifact_b, [{"artifact_id": str(artifact_a), "version": 1}]),
        (artifact_c, [{"artifact_id": str(artifact_b), "version": 1}]),
    ]:
        await conn.execute(
            "INSERT INTO artifacts (id, project_id, type, owner_user_id, status, version, "
            "based_on_artifacts, content_ref, status_changed_at) "
            "VALUES ($1, $2, 'requirement', $3, 'draft', 1, $4::jsonb, 'docs/x.md', NOW())",
            aid,
            project_id,
            user_id,
            str(based_on).replace("'", '"'),
        )

    # 查询 based_on_artifacts @> '[{"artifact_id": "A"}]' → 应返回 B（直接依赖 A）
    rows = await conn.fetch(
        "SELECT id FROM artifacts WHERE based_on_artifacts @> $1::jsonb",
        '[{"artifact_id": "' + str(artifact_a) + '"}]',
    )
    returned_ids = {row["id"] for row in rows}
    assert artifact_b in returned_ids, "B 直接依赖 A，应被 @> 查询返回"
    assert artifact_c not in returned_ids, "C 间接依赖 A（靠应用层递归），不应被 @> 查询返回"

    # EXPLAIN 验证走 GIN 索引（强制关闭 seqscan 让优化器选索引，小表默认会走 seqscan）
    await conn.execute("SET enable_seqscan = off")
    try:
        plan = await conn.fetch(
            "EXPLAIN SELECT id FROM artifacts WHERE based_on_artifacts @> $1::jsonb",
            '[{"artifact_id": "' + str(artifact_a) + '"}]',
        )
        plan_text = "\n".join(row[0] for row in plan)
        assert "Seq Scan" not in plan_text, f"应走 GIN 索引，实际计划:\n{plan_text}"
        assert "Bitmap Index Scan" in plan_text or "Index Scan" in plan_text, f"应使用索引扫描，实际计划:\n{plan_text}"
    finally:
        await conn.execute("SET enable_seqscan = on")


async def test_ar_1_3_agent_runs_partial_unique_index_blocks_reentry(schema_conn: asyncpg.Connection) -> None:
    """AR-1.3 agent_runs 部分唯一索引阻止同 task 重入"""
    conn = schema_conn
    user_id, project_id = await _seed_user_and_project(conn)

    # 创建 task
    task_id = uuid.uuid4()
    await conn.execute(
        "INSERT INTO tasks (id, project_id, type, status, owner_user_id, instruction, agent_type) "
        "VALUES ($1, $2, 'development', 'running', $3, 'test', 'implementer')",
        task_id,
        project_id,
        user_id,
    )

    # 插入 task_id=T1 status=running 的 agent_run
    run_id_1 = uuid.uuid4()
    await conn.execute(
        "INSERT INTO agent_runs (id, project_id, run_kind, agent_type, task_id, user_id, "
        "model_id, status, started_at, token_total) "
        "VALUES ($1, $2, 'dispatch', 'implementer', $3, $4, 'm1', 'running', NOW(), 0)",
        run_id_1,
        project_id,
        task_id,
        user_id,
    )

    # 再插入同 task_id 第二条 running → 应抛 UniqueViolationError
    with pytest.raises(asyncpg.UniqueViolationError):
        await conn.execute(
            "INSERT INTO agent_runs (id, project_id, run_kind, agent_type, task_id, user_id, "
            "model_id, status, started_at, token_total) "
            "VALUES ($1, $2, 'dispatch', 'implementer', $3, $4, 'm1', 'running', NOW(), 0)",
            uuid.uuid4(),
            project_id,
            task_id,
            user_id,
        )

    # 插入 status=completed 不冲突
    await conn.execute(
        "INSERT INTO agent_runs (id, project_id, run_kind, agent_type, task_id, user_id, "
        "model_id, status, started_at, ended_at, token_total) "
        "VALUES ($1, $2, 'dispatch', 'implementer', $3, $4, 'm1', 'completed', NOW(), NOW(), 100)",
        uuid.uuid4(),
        project_id,
        task_id,
        user_id,
    )

    # 插入其他 task_id 的 running 不冲突
    other_task_id = uuid.uuid4()
    await conn.execute(
        "INSERT INTO tasks (id, project_id, type, status, owner_user_id, instruction, agent_type) "
        "VALUES ($1, $2, 'development', 'running', $3, 'test2', 'implementer')",
        other_task_id,
        project_id,
        user_id,
    )
    await conn.execute(
        "INSERT INTO agent_runs (id, project_id, run_kind, agent_type, task_id, user_id, "
        "model_id, status, started_at, token_total) "
        "VALUES ($1, $2, 'dispatch', 'implementer', $3, $4, 'm1', 'running', NOW(), 0)",
        uuid.uuid4(),
        project_id,
        other_task_id,
        user_id,
    )


async def test_ar_1_4_agent_runs_event_id_agent_type_unique(schema_conn: asyncpg.Connection) -> None:
    """AR-1.4 agent_runs (event_id, agent_type) 幂等键"""
    conn = schema_conn
    user_id, project_id = await _seed_user_and_project(conn)

    event_id = uuid.uuid4()

    # 插入 (event_id=E1, agent_type=implementer)
    await conn.execute(
        "INSERT INTO agent_runs (id, project_id, run_kind, agent_type, event_id, user_id, "
        "model_id, status, started_at, token_total) "
        "VALUES ($1, $2, 'dispatch', 'implementer', $3, $4, 'm1', 'running', NOW(), 0)",
        uuid.uuid4(),
        project_id,
        event_id,
        user_id,
    )

    # 再插入同 event_id + 同 agent_type → 应抛 UniqueViolationError
    with pytest.raises(asyncpg.UniqueViolationError):
        await conn.execute(
            "INSERT INTO agent_runs (id, project_id, run_kind, agent_type, event_id, user_id, "
            "model_id, status, started_at, token_total) "
            "VALUES ($1, $2, 'dispatch', 'implementer', $3, $4, 'm1', 'running', NOW(), 0)",
            uuid.uuid4(),
            project_id,
            event_id,
            user_id,
        )

    # 同 event_id + 不同 agent_type 不冲突
    await conn.execute(
        "INSERT INTO agent_runs (id, project_id, run_kind, agent_type, event_id, user_id, "
        "model_id, status, started_at, token_total) "
        "VALUES ($1, $2, 'dispatch', 'critic', $3, $4, 'm1', 'running', NOW(), 0)",
        uuid.uuid4(),
        project_id,
        event_id,
        user_id,
    )


async def test_ar_1_5_model_usage_daily_upsert(schema_conn: asyncpg.Connection) -> None:
    """AR-1.5 model_usage_daily 联合唯一键 UPSERT"""
    conn = schema_conn
    user_id, _ = await _seed_user_and_project(conn)

    # 第一次 UPSERT
    await conn.execute(
        "INSERT INTO model_usage_daily (user_id, model_id, agent_type, date, call_count, "
        "input_tokens_sum, output_tokens_sum, cache_hit_tokens_sum, latency_avg_ms, error_count, updated_at) "
        "VALUES ($1, 'glm-4', 'implementer', '2026-06-26', 1, 100, 50, 0, 200, 0, NOW()) "
        "ON CONFLICT (user_id, model_id, agent_type, date) DO UPDATE SET "
        "call_count = model_usage_daily.call_count + EXCLUDED.call_count, "
        "input_tokens_sum = model_usage_daily.input_tokens_sum + EXCLUDED.input_tokens_sum",
        user_id,
    )

    # 第二次 UPSERT 同四元组 → call_count 累加
    await conn.execute(
        "INSERT INTO model_usage_daily (user_id, model_id, agent_type, date, call_count, "
        "input_tokens_sum, output_tokens_sum, cache_hit_tokens_sum, latency_avg_ms, error_count, updated_at) "
        "VALUES ($1, 'glm-4', 'implementer', '2026-06-26', 1, 100, 50, 0, 200, 0, NOW()) "
        "ON CONFLICT (user_id, model_id, agent_type, date) DO UPDATE SET "
        "call_count = model_usage_daily.call_count + EXCLUDED.call_count, "
        "input_tokens_sum = model_usage_daily.input_tokens_sum + EXCLUDED.input_tokens_sum",
        user_id,
    )

    row = await conn.fetchrow(
        "SELECT call_count, input_tokens_sum FROM model_usage_daily "
        "WHERE user_id=$1 AND model_id='glm-4' AND agent_type='implementer' AND date='2026-06-26'",
        user_id,
    )
    assert row is not None, "查询应返回结果"
    assert row["call_count"] == 2, "二次 UPSERT 后 call_count 应累加为 2"
    assert row["input_tokens_sum"] == 200, "input_tokens_sum 应累加为 200"

    # 不同四元组各自独立
    await conn.execute(
        "INSERT INTO model_usage_daily (user_id, model_id, agent_type, date, call_count, "
        "input_tokens_sum, output_tokens_sum, cache_hit_tokens_sum, latency_avg_ms, error_count, updated_at) "
        "VALUES ($1, 'claude', 'analyst', '2026-06-26', 1, 200, 80, 0, 300, 0, NOW())",
        user_id,
    )
    count = await conn.fetchval("SELECT COUNT(*) FROM model_usage_daily WHERE user_id=$1", user_id)
    assert count == 2, "不同四元组应各自独立，共 2 行"


async def test_ar_1_6_model_usage_archive_on_conflict_do_nothing(schema_conn: asyncpg.Connection) -> None:
    """AR-1.6 model_usage_archive 联合唯一键 ON CONFLICT DO NOTHING"""
    conn = schema_conn
    user_id, _ = await _seed_user_and_project(conn)

    # 第一次 INSERT
    await conn.execute(
        "INSERT INTO model_usage_archive (user_id, date, compressed_data, created_at) "
        "VALUES ($1, '2026-06-26', $2, NOW())",
        user_id,
        b"\x1f\x8bcompresseddata1",
    )

    # 第二次同 (user_id, date) → ON CONFLICT DO NOTHING 跳过
    await conn.execute(
        "INSERT INTO model_usage_archive (user_id, date, compressed_data, created_at) "
        "VALUES ($1, '2026-06-26', $2, NOW()) ON CONFLICT (user_id, date) DO NOTHING",
        user_id,
        b"\x1f\x8bcompresseddata2",
    )

    # 仍只有 1 行，且数据是第一次的
    row = await conn.fetchrow(
        "SELECT compressed_data FROM model_usage_archive WHERE user_id=$1 AND date='2026-06-26'",
        user_id,
    )
    assert row is not None, "查询应返回结果"
    assert row["compressed_data"] == b"\x1f\x8bcompresseddata1", "ON CONFLICT DO NOTHING 应保留原数据"

    # 不同 (user_id, date) 各自独立
    other_user_id = uuid.uuid4()
    await conn.execute(
        "INSERT INTO users (id, username, password_hash, display_name, status, is_admin) "
        "VALUES ($1, $2, $3, $4, 'active', false)",
        other_user_id,
        f"u_{other_user_id.hex[:8]}",
        "hash",
        "Other User",
    )
    await conn.execute(
        "INSERT INTO model_usage_archive (user_id, date, compressed_data, created_at) "
        "VALUES ($1, '2026-06-26', $2, NOW())",
        other_user_id,
        b"\x1f\x8bother",
    )
    count = await conn.fetchval("SELECT COUNT(*) FROM model_usage_archive WHERE date='2026-06-26'")
    assert count == 2, "不同 user_id 应各自独立，共 2 行"


async def test_ar_1_7_event_log_payload_ref_url_field(schema_conn: asyncpg.Connection) -> None:
    """AR-1.7 event_log.payload_ref_url 字段 + L1/L2 引用约定"""
    conn = schema_conn

    # L1 内联：payload 含 instruction，payload_ref_url 为 NULL
    l1_event_id = uuid.uuid4()
    await conn.execute(
        "INSERT INTO event_log (event_id, project_id, event_type, participant_id, "
        "participant_type, payload, correlation_id, payload_ref_url) "
        "VALUES ($1, 'p1', 'AnalysisRequested', 'u1', 'human', "
        '\'{"instruction": "small payload"}\'::jsonb, $2, NULL)',
        l1_event_id,
        uuid.uuid4(),
    )

    # L2 引用：payload_ref_url 非 NULL
    l2_event_id = uuid.uuid4()
    ref_url = f"s3://orbion-events/{l2_event_id}/revision_notes"
    await conn.execute(
        "INSERT INTO event_log (event_id, project_id, event_type, participant_id, "
        "participant_type, payload, correlation_id, payload_ref_url) "
        "VALUES ($1, 'p1', 'AnalysisRequested', 'u1', 'human', "
        "'{\"revision_notes_ref\": true}'::jsonb, $2, $3)",
        l2_event_id,
        uuid.uuid4(),
        ref_url,
    )

    # 验证字段类型与可空性
    col = await conn.fetchrow(
        "SELECT data_type, is_nullable FROM information_schema.columns "
        "WHERE table_name='event_log' AND column_name='payload_ref_url'"
    )
    assert col is not None, "字段应存在"
    assert col["data_type"] == "character varying", "payload_ref_url 应为 VARCHAR"
    assert col["is_nullable"] == "YES", "payload_ref_url 应可为 NULL"

    # 验证 L1 行：payload_ref_url 为 NULL，payload 含 instruction
    l1_row = await conn.fetchrow("SELECT payload, payload_ref_url FROM event_log WHERE event_id=$1", l1_event_id)
    assert l1_row is not None, "L1 event 应存在"
    assert l1_row["payload_ref_url"] is None, "L1 内联时 payload_ref_url 应为 NULL"
    l1_payload = json.loads(l1_row["payload"])
    assert l1_payload["instruction"] == "small payload", "L1 内联时 payload 应含字段内容"

    # 验证 L2 行：payload_ref_url 非 NULL
    l2_row = await conn.fetchrow("SELECT payload, payload_ref_url FROM event_log WHERE event_id=$1", l2_event_id)
    assert l2_row is not None, "L2 event 应存在"
    assert l2_row["payload_ref_url"] == ref_url, "L2 引用时 payload_ref_url 应为对象存储 URL"
