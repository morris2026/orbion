"""PostgresThreadRead — PostgreSQL投影表读端实现"""

import uuid
from typing import Any

import asyncpg

from app.biz.threads.read_repo import ThreadReadProtocol
from app.config import get_settings

_MSG_NOT_CONNECTED = "PostgresThreadRead未连接，请先调用connect()"


class PostgresThreadRead(ThreadReadProtocol):
    """PostgreSQL线程读端实现"""

    def __init__(self) -> None:
        settings = get_settings()
        self._url = settings.postgres.url
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        self._pool = await asyncpg.create_pool(self._url, min_size=2, max_size=10)

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None

    def _require_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError(_MSG_NOT_CONNECTED)
        return self._pool

    async def insert_thread(self, thread_id: str, project_id: str, title: str, type: str, created_by: str) -> None:
        """直接写入threads表行 — CQRS写端需要线程记录存在才能让thread_messages FK约束通过"""
        pool = self._require_pool()
        await pool.execute(
            "INSERT INTO threads (id, project_id, title, status, type, created_by, created_at) "
            "VALUES ($1, $2, $3, 'active', $4, $5, NOW()) "
            "ON CONFLICT (id) DO NOTHING",
            uuid.UUID(thread_id),
            uuid.UUID(project_id),
            title,
            type,
            created_by,
        )

    async def list_threads(self, project_id: str) -> list[dict[str, Any]]:
        """线程列表含聚合字段：has_summary、pending_plan_count、message_count"""
        pool = self._require_pool()
        rows = await pool.fetch(
            """SELECT t.id, t.title, t.status, t.type, t.created_at,
               EXISTS(
                   SELECT 1 FROM thread_messages tm
                   WHERE tm.thread_id = t.id AND tm.event_type = 'DiscussionSummaryGenerated'
               ) AS has_summary,
               (
                   SELECT COUNT(*) FROM execution_plans ep
                   WHERE ep.thread_id = t.id AND ep.status = 'proposed'
               ) AS pending_plan_count,
               (
                   SELECT COUNT(*) FROM thread_messages tm
                   WHERE tm.thread_id = t.id
               ) AS message_count
               FROM threads t
               WHERE t.project_id = $1
               ORDER BY t.created_at DESC""",
            uuid.UUID(project_id),
        )
        results = [_row_to_dict(r) for r in rows]
        # asyncpg返回BIGINT，转为int
        for r in results:
            r["has_summary"] = bool(r["has_summary"])
            r["pending_plan_count"] = int(r["pending_plan_count"])
            r["message_count"] = int(r["message_count"])
        return results

    async def get_messages(self, thread_id: str, before: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        """游标分页获取消息列表 — 默认50条，before参数取指定ID之前的消息"""
        pool = self._require_pool()
        # 限制limit最大100
        actual_limit = min(limit, 100)
        if before is not None:
            # 获取指定ID之前的消息（逆序时间线）
            rows = await pool.fetch(
                """SELECT id, thread_id, project_id, participant_id, participant_type,
                   display_name, content, event_type, created_at
                   FROM thread_messages
                   WHERE thread_id = $1 AND created_at < (
                       SELECT created_at FROM thread_messages WHERE id = $2
                   )
                   ORDER BY created_at DESC
                   LIMIT $3""",
                uuid.UUID(thread_id),
                uuid.UUID(before),
                actual_limit,
            )
            # 逆序结果翻转为时间正序
            results = [_row_to_dict(r) for r in reversed(rows)]
        else:
            # 获取最近的消息（时间正序，限制条数取最近的N条）
            rows = await pool.fetch(
                """SELECT id, thread_id, project_id, participant_id, participant_type,
                   display_name, content, event_type, created_at
                   FROM thread_messages
                   WHERE thread_id = $1
                   ORDER BY created_at DESC
                   LIMIT $2""",
                uuid.UUID(thread_id),
                actual_limit,
            )
            # 逆序结果翻转为时间正序
            results = [_row_to_dict(r) for r in reversed(rows)]
        return results

    async def check_thread_in_project(self, thread_id: str, project_id: str) -> bool:
        """验证线程属于指定项目"""
        pool = self._require_pool()
        row = await pool.fetchrow(
            "SELECT 1 FROM threads WHERE id = $1 AND project_id = $2",
            uuid.UUID(thread_id),
            uuid.UUID(project_id),
        )
        return row is not None

    async def check_member_exists(self, project_id: str, user_id: str) -> bool:
        """检查用户是否为项目成员"""
        pool = self._require_pool()
        row = await pool.fetchrow(
            "SELECT 1 FROM project_members WHERE participant_id = $1 AND project_id = $2 AND type = 'human'",
            user_id,
            uuid.UUID(project_id),
        )
        return row is not None

    async def get_thread_project_id(self, thread_id: str) -> str | None:
        """通过thread_id查找project_id — 消息端点路径不含project_id"""
        pool = self._require_pool()
        row = await pool.fetchrow(
            "SELECT project_id FROM threads WHERE id = $1",
            uuid.UUID(thread_id),
        )
        return str(row["project_id"]) if row else None


def _row_to_dict(row: asyncpg.Record) -> dict[str, Any]:
    """asyncpg Record → dict，UUID列自动转为str"""
    result: dict[str, Any] = dict(row)
    for key, value in result.items():
        if isinstance(value, uuid.UUID):
            result[key] = str(value)
    return result
