"""TC-4.1–TC-4.6: Event Store PostgreSQL持久化"""

import json
from collections.abc import AsyncGenerator
from typing import Any, Literal
from uuid import UUID, uuid4

import asyncpg
import pytest
from asyncpg.exceptions import UniqueViolationError

from app.config import Settings
from app.hub.events.store import EventStore
from app.hub.events.types import Event


@pytest.fixture
async def event_store() -> AsyncGenerator[EventStore, None]:
    """创建EventStore实例，连接数据库"""
    settings = Settings()
    store = EventStore(settings.postgres_url)
    await store.connect()
    yield store
    await store.close()


@pytest.fixture
async def clean_event_log(event_store: EventStore) -> EventStore:
    """清空event_log表，确保测试数据隔离"""
    conn: asyncpg.Connection = await asyncpg.connect(Settings().postgres_url)
    try:
        await conn.execute("DELETE FROM event_log")
    finally:
        await conn.close()
    return event_store


def make_event(
    event_id: str | None = None,
    project_id: str = "proj-1",
    event_type: str = "DiscussionMessageCreated",
    participant_id: str = "user-1",
    participant_type: Literal["human", "agent"] = "human",
    payload: dict[str, Any] | None = None,
    correlation_id: str | None = None,
    causation_id: str | None = None,
) -> Event:
    """构造测试Event实例，UUID字段使用标准格式"""
    return Event(
        event_id=event_id or str(uuid4()),
        project_id=project_id,
        event_type=event_type,
        participant_id=participant_id,
        participant_type=participant_type,
        payload=payload or {"data": "test"},
        correlation_id=correlation_id or str(uuid4()),
        causation_id=causation_id,
    )


class TestEventStoreAppend:
    """TC-4.1: append写入事件"""

    async def test_append_writes_event_to_event_log(self, clean_event_log: EventStore) -> None:
        event = make_event()
        await clean_event_log.append(event)

        conn = await asyncpg.connect(Settings().postgres_url)
        try:
            row = await conn.fetchrow("SELECT * FROM event_log WHERE event_id = $1", UUID(event.event_id))
        finally:
            await conn.close()

        assert row is not None
        assert str(row["event_id"]) == event.event_id
        assert row["project_id"] == event.project_id
        assert row["event_type"] == event.event_type
        assert row["participant_id"] == event.participant_id
        assert row["participant_type"] == event.participant_type
        assert json.loads(row["payload"])["data"] == "test"
        assert str(row["correlation_id"]) == event.correlation_id
        assert row["created_at"] is not None


class TestEventStoreGetByCorrelation:
    """TC-4.2: get_events_by_correlation按链路查询"""

    async def test_returns_events_with_same_correlation_id_sorted_by_time(self, clean_event_log: EventStore) -> None:
        corr_id = str(uuid4())
        events = [
            make_event(event_type="DiscussionMessageCreated", correlation_id=corr_id),
            make_event(event_type="DiscussionSummaryGenerated", correlation_id=corr_id),
            make_event(event_type="ExecutionPlanProposed", correlation_id=corr_id),
        ]
        for event in events:
            await clean_event_log.append(event)

        result = await clean_event_log.get_events_by_correlation(corr_id)

        assert len(result) == 3
        assert [e.event_type for e in result] == [
            "DiscussionMessageCreated",
            "DiscussionSummaryGenerated",
            "ExecutionPlanProposed",
        ]


class TestEventStoreProjectIsolation:
    """TC-4.3: get_events_by_project项目边界硬隔离"""

    async def test_returns_only_events_from_target_project(self, clean_event_log: EventStore) -> None:
        await clean_event_log.append(make_event(project_id="proj-A"))
        await clean_event_log.append(make_event(project_id="proj-A"))
        await clean_event_log.append(make_event(project_id="proj-B"))

        result = await clean_event_log.get_events_by_project("proj-A")

        assert len(result) == 2
        assert all(e.project_id == "proj-A" for e in result)


class TestEventStoreEventTypeFilter:
    """TC-4.4: event_type可选过滤"""

    async def test_filters_by_event_type(self, clean_event_log: EventStore) -> None:
        await clean_event_log.append(make_event(project_id="proj-X", event_type="DiscussionMessageCreated"))
        await clean_event_log.append(make_event(project_id="proj-X", event_type="DiscussionSummaryGenerated"))
        await clean_event_log.append(make_event(project_id="proj-X", event_type="DiscussionMessageCreated"))

        result = await clean_event_log.get_events_by_project("proj-X", event_type="DiscussionMessageCreated")

        assert len(result) == 2
        assert all(e.event_type == "DiscussionMessageCreated" for e in result)


class TestEventStoreCausationIdNull:
    """TC-4.5: causation_id为null的事件"""

    async def test_causation_id_null_stored_and_retrieved(self, clean_event_log: EventStore) -> None:
        event = make_event(causation_id=None)
        await clean_event_log.append(event)

        result = await clean_event_log.get_events_by_project("proj-1")

        assert len(result) == 1
        assert result[0].causation_id is None

        conn = await asyncpg.connect(Settings().postgres_url)
        try:
            row = await conn.fetchrow(
                "SELECT causation_id FROM event_log WHERE event_id = $1",
                UUID(event.event_id),
            )
        finally:
            await conn.close()

        assert row is not None
        assert row["causation_id"] is None


class TestEventStoreDuplicateEventId:
    """TC-4.6: 重复event_id写入"""

    async def test_duplicate_event_id_fails_without_corrupting_first_record(self, clean_event_log: EventStore) -> None:
        dup_id = str(uuid4())
        event1 = make_event(event_id=dup_id, project_id="proj-1")
        await clean_event_log.append(event1)

        event2 = make_event(event_id=dup_id, project_id="proj-2")
        with pytest.raises(UniqueViolationError):
            await clean_event_log.append(event2)

        result = await clean_event_log.get_events_by_project("proj-1")
        assert len(result) == 1
        assert result[0].project_id == "proj-1"
