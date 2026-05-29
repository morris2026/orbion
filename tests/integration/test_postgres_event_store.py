"""PostgresEventStore实现特有行为验证"""

import json
from collections.abc import AsyncGenerator
from typing import Any, Literal
from uuid import UUID, uuid4

import pytest
from asyncpg.exceptions import UniqueViolationError

from app.hub.events.postgres_store import PostgresEventStore
from app.hub.events.types import Event


@pytest.fixture
async def postgres_store() -> AsyncGenerator[PostgresEventStore, None]:
    store = PostgresEventStore()
    await store.connect()
    yield store
    await store.close()


@pytest.fixture
async def clean_event_log(postgres_store: PostgresEventStore) -> PostgresEventStore:
    """用store自己的pool清理event_log"""
    async with postgres_store.pool.acquire() as conn:
        await conn.execute("DELETE FROM event_log")
    return postgres_store


def make_event(
    event_id: str | None = None,
    project_id: str | None = None,
    event_type: str = "DiscussionMessageCreated",
    participant_id: str = "user-1",
    participant_type: Literal["human", "agent"] = "human",
    payload: dict[str, Any] | None = None,
    correlation_id: str | None = None,
    causation_id: str | None = None,
) -> Event:
    """构造测试Event实例"""
    return Event(
        event_id=event_id or str(uuid4()),
        project_id=project_id or str(uuid4()),
        event_type=event_type,
        participant_id=participant_id,
        participant_type=participant_type,
        payload=payload or {"data": "test"},
        correlation_id=correlation_id or str(uuid4()),
        causation_id=causation_id,
    )


async def test_append_writes_row_to_event_log(clean_event_log: PostgresEventStore) -> None:
    """验证append写入的数据库行结构与字段值"""
    event = make_event()
    await clean_event_log.append(event)

    async with clean_event_log.pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM event_log WHERE event_id = $1", UUID(event.event_id))

    assert row is not None
    assert str(row["event_id"]) == event.event_id
    assert row["project_id"] == event.project_id
    assert row["event_type"] == event.event_type
    assert row["participant_id"] == event.participant_id
    assert row["participant_type"] == event.participant_type
    assert json.loads(row["payload"])["data"] == "test"
    assert str(row["correlation_id"]) == event.correlation_id
    assert row["created_at"] is not None


async def test_duplicate_event_id_raises_unique_violation(clean_event_log: PostgresEventStore) -> None:
    """验证重复event_id触发UniqueViolationError"""
    dup_id = str(uuid4())
    event1 = make_event(event_id=dup_id)
    await clean_event_log.append(event1)

    event2 = make_event(event_id=dup_id)
    with pytest.raises(UniqueViolationError):
        await clean_event_log.append(event2)
