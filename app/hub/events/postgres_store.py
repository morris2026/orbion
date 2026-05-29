"""PostgresEventStore — PostgreSQL event_log表持久化实现"""

import json
from typing import Any
from uuid import UUID

import asyncpg

from app.config import get_settings
from app.hub.events.store import EventStoreProtocol
from app.hub.events.types import Event


class PostgresEventStore(EventStoreProtocol):
    """PostgreSQL event_log表持久化实现"""

    def __init__(self) -> None:
        settings = get_settings()
        self._url = settings.postgres.url
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        self._pool = await asyncpg.create_pool(self._url, min_size=2, max_size=10)

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()

    @property
    def pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError(self._MSG_NOT_CONNECTED)
        return self._pool

    _MSG_NOT_CONNECTED = "PostgresEventStore未连接，请先调用connect()"

    async def append(self, event: Event) -> None:
        if self._pool is None:
            raise RuntimeError(self._MSG_NOT_CONNECTED)
        await self._pool.execute(
            "INSERT INTO event_log "
            "(event_id, project_id, event_type, participant_id, participant_type, "
            "payload, correlation_id, causation_id) "
            "VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8)",
            UUID(event.event_id),  # asyncpg要求UUID列用Python UUID对象
            event.project_id,
            event.event_type,
            event.participant_id,
            event.participant_type,
            json.dumps(event.payload),  # asyncpg要求JSONB列先序列化再::jsonb cast
            UUID(event.correlation_id),
            UUID(event.causation_id) if event.causation_id else None,
        )

    async def get_events_by_correlation(self, correlation_id: str, limit: int = 100) -> list[Event]:
        if self._pool is None:
            raise RuntimeError(self._MSG_NOT_CONNECTED)
        rows = await self._pool.fetch(
            "SELECT * FROM event_log WHERE correlation_id = $1 ORDER BY created_at ASC LIMIT $2",
            UUID(correlation_id),
            limit,
        )
        return [_row_to_event(row) for row in rows]

    async def get_events_by_project(
        self, project_id: str, event_type: str | None = None, limit: int = 50
    ) -> list[Event]:
        if self._pool is None:
            raise RuntimeError(self._MSG_NOT_CONNECTED)
        if event_type is not None:
            rows = await self._pool.fetch(
                "SELECT * FROM event_log WHERE project_id = $1 AND event_type = $2 ORDER BY created_at DESC LIMIT $3",
                project_id,
                event_type,
                limit,
            )
        else:
            rows = await self._pool.fetch(
                "SELECT * FROM event_log WHERE project_id = $1 ORDER BY created_at DESC LIMIT $2",
                project_id,
                limit,
            )
        return [_row_to_event(row) for row in rows]


def _row_to_event(row: asyncpg.Record) -> Event:
    record: dict[str, Any] = dict(row)
    # asyncpg返回UUID对象，转换为str以匹配Event模型
    for key in ("event_id", "correlation_id", "causation_id"):
        if record.get(key) is not None:
            record[key] = str(record[key])
    # asyncpg返回JSONB为str，反序列化为dict；若未来版本直接返回dict则无需转换
    payload = record.get("payload")
    if isinstance(payload, str):
        record["payload"] = json.loads(payload)
    elif isinstance(payload, dict):
        pass
    return Event(**record)
