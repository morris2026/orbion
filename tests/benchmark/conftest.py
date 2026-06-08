"""性能基准测试conftest — 共享fixture、事件构造函数、基线数据持久化

DB TRUNCATE和env/app.state清理已移至根conftest _clean_env fixture统一处理。
"""

import json
import os
from collections.abc import AsyncGenerator, Generator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from app.hub.channels.sse import SSEChannel
from app.hub.events.bus import InProcessEventBus
from app.hub.events.postgres_projections import PostgresEventProjections
from app.hub.events.postgres_store import PostgresEventStore
from app.hub.events.types import Event

BASELINE_FILE = Path(__file__).resolve().parent / "baseline.json"

# 环境变量ORBION_BENCHMARK_PERSIST=1时持久化到JSON，默认只打印
PERSIST = os.environ.get("ORBION_BENCHMARK_PERSIST", "") == "1"


@pytest.fixture(scope="session")
def benchmark_results() -> Generator[list[dict[str, Any]], None, None]:
    """Session级基线数据收集器：每个TC注册结果，session结束时按PERSIST决定是否持久化"""
    results: list[dict[str, Any]] = []
    yield results
    if PERSIST and results:
        output = {
            "timestamp": datetime.now(timezone.utc).isoformat(),  # noqa: UP017
            "n_events_per_round": 100,
            "n_rounds": 5,
            "results": results,
        }
        BASELINE_FILE.write_text(json.dumps(output, indent=2, ensure_ascii=False))
        print(f"\n基线数据已持久化: {BASELINE_FILE}")


@pytest.fixture
async def event_store() -> AsyncGenerator[PostgresEventStore, None]:
    store = PostgresEventStore()
    await store.connect()
    yield store
    await store.close()


@pytest.fixture
async def event_bus() -> InProcessEventBus:
    return InProcessEventBus()


@pytest.fixture
async def projections(event_bus: InProcessEventBus) -> AsyncGenerator[PostgresEventProjections, None]:
    proj = PostgresEventProjections(event_bus)
    await proj.connect()
    yield proj
    await proj.close()


@pytest.fixture
async def sse_channel(event_bus: InProcessEventBus) -> SSEChannel:
    return SSEChannel(event_bus)


def make_bench_event(
    event_id: str | None = None,
    project_id: str | None = None,
    event_type: str = "DiscussionMessageCreated",
    participant_id: str = "user-1",
    correlation_id: str | None = None,
    payload: dict[str, object] | None = None,
) -> Event:
    return Event(
        event_id=event_id or str(uuid4()),
        project_id=project_id or str(uuid4()),
        event_type=event_type,
        participant_id=participant_id,
        participant_type="human",
        payload=payload or {"data": "bench"},
        correlation_id=correlation_id or str(uuid4()),
    )
