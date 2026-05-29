"""TC-4.1–TC-4.6: EventStore能力验证 — 遍历注册表中所有实现"""

from collections.abc import AsyncGenerator
from typing import Any, Literal
from uuid import uuid4

import pytest

from app.hub.events.store import STORE_IMPLEMENTATIONS, EventStoreProtocol, load_store_impl
from app.hub.events.types import Event


@pytest.fixture(params=list(STORE_IMPLEMENTATIONS.keys()))
async def event_store(request: pytest.FixtureRequest) -> AsyncGenerator[EventStoreProtocol, None]:
    """创建已连接的EventStore实例，遍历所有注册实现"""
    impl_cls = load_store_impl(request.param)
    store: EventStoreProtocol = impl_cls()
    await store.connect()
    yield store
    await store.close()


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


class TestEventStoreAppend:
    """TC-4.1: append写入事件可通过接口完整检索"""

    async def test_append_and_retrieve_event(self, event_store: EventStoreProtocol) -> None:
        event = make_event()
        await event_store.append(event)

        result = await event_store.get_events_by_project(event.project_id)
        assert len(result) == 1
        retrieved = result[0]
        assert retrieved.event_id == event.event_id
        assert retrieved.project_id == event.project_id
        assert retrieved.event_type == event.event_type
        assert retrieved.participant_id == event.participant_id
        assert retrieved.participant_type == event.participant_type
        assert retrieved.payload == event.payload
        assert retrieved.correlation_id == event.correlation_id
        assert retrieved.causation_id == event.causation_id


class TestEventStoreGetByCorrelation:
    """TC-4.2: get_events_by_correlation按链路查询"""

    async def test_returns_events_with_same_correlation_id_sorted_by_time(
        self, event_store: EventStoreProtocol
    ) -> None:
        corr_id = str(uuid4())
        project_id = str(uuid4())
        events = [
            make_event(project_id=project_id, event_type="DiscussionMessageCreated", correlation_id=corr_id),
            make_event(project_id=project_id, event_type="DiscussionSummaryGenerated", correlation_id=corr_id),
            make_event(project_id=project_id, event_type="ExecutionPlanProposed", correlation_id=corr_id),
        ]
        for event in events:
            await event_store.append(event)

        result = await event_store.get_events_by_correlation(corr_id)
        assert len(result) == 3
        assert [e.event_type for e in result] == [
            "DiscussionMessageCreated",
            "DiscussionSummaryGenerated",
            "ExecutionPlanProposed",
        ]


class TestEventStoreProjectIsolation:
    """TC-4.3: get_events_by_project项目边界硬隔离"""

    async def test_returns_only_events_from_target_project(self, event_store: EventStoreProtocol) -> None:
        proj_a = str(uuid4())
        proj_b = str(uuid4())
        await event_store.append(make_event(project_id=proj_a))
        await event_store.append(make_event(project_id=proj_a))
        await event_store.append(make_event(project_id=proj_b))

        result = await event_store.get_events_by_project(proj_a)
        assert len(result) == 2
        assert all(e.project_id == proj_a for e in result)


class TestEventStoreEventTypeFilter:
    """TC-4.4: event_type可选过滤"""

    async def test_filters_by_event_type(self, event_store: EventStoreProtocol) -> None:
        project_id = str(uuid4())
        await event_store.append(make_event(project_id=project_id, event_type="DiscussionMessageCreated"))
        await event_store.append(make_event(project_id=project_id, event_type="DiscussionSummaryGenerated"))
        await event_store.append(make_event(project_id=project_id, event_type="DiscussionMessageCreated"))

        result = await event_store.get_events_by_project(project_id, event_type="DiscussionMessageCreated")
        assert len(result) == 2
        assert all(e.event_type == "DiscussionMessageCreated" for e in result)


class TestEventStoreCausationIdNull:
    """TC-4.5: causation_id为null的事件"""

    async def test_causation_id_null_stored_and_retrieved(self, event_store: EventStoreProtocol) -> None:
        event = make_event(causation_id=None)
        await event_store.append(event)

        result = await event_store.get_events_by_project(event.project_id)
        assert len(result) == 1
        assert result[0].causation_id is None


class TestEventStoreDuplicateEventId:
    """TC-4.6: 重复event_id写入"""

    async def test_duplicate_event_id_fails_without_corrupting_first_record(
        self, event_store: EventStoreProtocol
    ) -> None:
        dup_id = str(uuid4())
        event1 = make_event(event_id=dup_id)
        await event_store.append(event1)

        event2 = make_event(event_id=dup_id)
        with pytest.raises(Exception):
            await event_store.append(event2)

        result = await event_store.get_events_by_project(event1.project_id)
        assert len(result) == 1
        assert result[0].project_id == event1.project_id
