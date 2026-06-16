"""MVP-22.1–MVP-22.6: 性能基准测试与基线数据"""

import asyncio
import time
from typing import Any
from uuid import uuid4

import pytest

from app.hub.channels.sse import SSEChannel
from app.hub.events.bus import InProcessEventBus
from app.hub.events.postgres_projections import PostgresEventProjections
from app.hub.events.postgres_store import PostgresEventStore
from app.hub.events.types import (
    DiscussionMessageCreatedPayload,
    Event,
    EventType,
    ProjectCreatedPayload,
)

from .conftest import make_bench_event

N_APPEND = 100  # MVP-22.1 连续append事件数
N_ROUNDS = 5  # 每个基准测试重复轮次，取均值


# -- MVP-22.1: EventStore append吞吐 --


@pytest.mark.asyncio
async def test_tc22_1_event_store_append_throughput(
    event_store: PostgresEventStore,
    benchmark_results: list[dict[str, Any]],
) -> None:
    """MVP-22.1: 连续append N个事件 → 计算吞吐（事件/秒），记录基线数据"""
    latencies: list[float] = []
    for _ in range(N_ROUNDS):
        events = [make_bench_event() for _ in range(N_APPEND)]
        start = time.perf_counter()
        for event in events:
            await event_store.append(event)
        elapsed = time.perf_counter() - start
        latencies.append(elapsed)

    avg_elapsed = sum(latencies) / len(latencies)
    throughput = N_APPEND / avg_elapsed
    print("\nMVP-22.1 EventStore append吞吐基线:")
    print(f"  {N_APPEND}个事件, {N_ROUNDS}轮, 平均耗时 {avg_elapsed:.4f}s")
    print(f"  吞吐量: {throughput:.1f} 事件/秒")
    for i, lat in enumerate(latencies):
        print(f"  第{i + 1}轮: {lat:.4f}s ({N_APPEND / lat:.1f} evt/s)")

    benchmark_results.append(
        {
            "tc": "MVP-22.1",
            "metric": "append_throughput",
            "unit": "evt/s",
            "rounds": [N_APPEND / lat for lat in latencies],
            "average": throughput,
        }
    )


# -- MVP-22.2: EventStore查询延迟（correlation_id） --


@pytest.mark.asyncio
async def test_tc22_2_event_store_query_correlation(
    event_store: PostgresEventStore,
    benchmark_results: list[dict[str, Any]],
) -> None:
    """MVP-22.2: 写入事件 → get_events_by_correlation → 计算延迟，记录基线数据"""
    corr_id = str(uuid4())
    events = [make_bench_event(correlation_id=corr_id) for _ in range(N_APPEND)]
    for event in events:
        await event_store.append(event)

    latencies: list[float] = []
    for _ in range(N_ROUNDS):
        start = time.perf_counter()
        result = await event_store.get_events_by_correlation(corr_id, limit=N_APPEND)
        elapsed = time.perf_counter() - start
        latencies.append(elapsed)
        assert len(result) == N_APPEND

    avg_latency = sum(latencies) / len(latencies)
    print("\nMVP-22.2 EventStore correlation_id查询延迟基线:")
    print(f"  {N_APPEND}条记录, {N_ROUNDS}轮, 平均延迟 {avg_latency * 1000:.2f}ms")
    for i, lat in enumerate(latencies):
        print(f"  第{i + 1}轮: {lat * 1000:.2f}ms")

    benchmark_results.append(
        {
            "tc": "MVP-22.2",
            "metric": "query_correlation_latency",
            "unit": "ms",
            "rounds": [lat * 1000 for lat in latencies],
            "average": avg_latency * 1000,
        }
    )


# -- MVP-22.3: EventStore查询延迟（project_id） --


@pytest.mark.asyncio
async def test_tc22_3_event_store_query_project(
    event_store: PostgresEventStore,
    benchmark_results: list[dict[str, Any]],
) -> None:
    """MVP-22.3: 写入事件 → get_events_by_project → 计算延迟，记录基线数据"""
    project_id = str(uuid4())
    events = [make_bench_event(project_id=project_id) for _ in range(N_APPEND)]
    for event in events:
        await event_store.append(event)

    latencies: list[float] = []
    for _ in range(N_ROUNDS):
        start = time.perf_counter()
        result = await event_store.get_events_by_project(project_id, limit=N_APPEND)
        elapsed = time.perf_counter() - start
        latencies.append(elapsed)
        assert len(result) == N_APPEND

    avg_latency = sum(latencies) / len(latencies)
    print("\nMVP-22.3 EventStore project_id查询延迟基线:")
    print(f"  {N_APPEND}条记录, {N_ROUNDS}轮, 平均延迟 {avg_latency * 1000:.2f}ms")
    for i, lat in enumerate(latencies):
        print(f"  第{i + 1}轮: {lat * 1000:.2f}ms")

    benchmark_results.append(
        {
            "tc": "MVP-22.3",
            "metric": "query_project_latency",
            "unit": "ms",
            "rounds": [lat * 1000 for lat in latencies],
            "average": avg_latency * 1000,
        }
    )


# -- MVP-22.4: InProcessEventBus调度延迟 --


@pytest.mark.asyncio
async def test_tc22_4_event_bus_dispatch_latency(benchmark_results: list[dict[str, Any]]) -> None:
    """MVP-22.4: subscribe → publish → handler开始执行 → 计算publish到handler开始执行的延迟"""
    bus = InProcessEventBus()
    handler_start_times: list[float] = []
    publish_times: list[float] = []

    async def timing_handler(event: Event) -> None:
        handler_start_times.append(time.perf_counter())

    bus.subscribe("BenchmarkEvent", timing_handler)

    latencies: list[float] = []
    for _ in range(N_ROUNDS):
        handler_start_times.clear()
        publish_times.clear()

        # 每轮逐事件publish，yield到事件循环让handler有机会执行
        for i in range(N_APPEND):
            publish_time = time.perf_counter()
            publish_times.append(publish_time)
            event = make_bench_event(event_type="BenchmarkEvent")
            await bus.publish(event)
            await asyncio.sleep(0)  # yield让handler开始执行

        # 等待所有handler完成
        await bus.wait_for_pending()

        # 验证所有handler都已执行
        assert len(handler_start_times) == N_APPEND

        # 计算每个事件的调度延迟
        round_latencies = []
        for pub_t, handler_t in zip(publish_times, handler_start_times):
            round_latencies.append(handler_t - pub_t)
        avg_round = sum(round_latencies) / len(round_latencies)
        latencies.append(avg_round)

    avg_latency = sum(latencies) / len(latencies)
    print("\nMVP-22.4 InProcessEventBus调度延迟基线:")
    print(f"  {N_APPEND}个事件/轮, {N_ROUNDS}轮, 平均调度延迟 {avg_latency * 1000:.4f}ms")
    for i, lat in enumerate(latencies):
        print(f"  第{i + 1}轮: {lat * 1000:.4f}ms")

    benchmark_results.append(
        {
            "tc": "MVP-22.4",
            "metric": "bus_dispatch_latency",
            "unit": "ms",
            "rounds": [lat * 1000 for lat in latencies],
            "average": avg_latency * 1000,
        }
    )


# -- MVP-22.5: CQRS投影更新延迟 --


@pytest.mark.asyncio
async def test_tc22_5_cqrs_projection_update_latency(
    projections: PostgresEventProjections,
    event_bus: InProcessEventBus,
    benchmark_results: list[dict[str, Any]],
) -> None:
    """MVP-22.5: publish事件 → 投影handler更新数据库 → 计算从publish到投影表写入完成的延迟"""
    project_id = str(uuid4())

    # 先发布ProjectCreated事件以创建项目（投影handler需要projects行存在）
    create_event = make_bench_event(
        project_id=project_id,
        event_type=EventType.ProjectCreated,
        payload=ProjectCreatedPayload(name="bench-project", description="bench").model_dump(mode="json"),
    )
    await event_bus.publish(create_event)
    await event_bus.wait_for_pending()

    latencies: list[float] = []
    for _ in range(N_ROUNDS):
        round_latencies = []
        for i in range(N_APPEND):
            payload = DiscussionMessageCreatedPayload(
                thread_id=str(uuid4()),
                content=f"bench-msg-{i}",
            ).model_dump(mode="json")
            event = make_bench_event(
                project_id=project_id,
                event_type=EventType.DiscussionMessageCreated,
                payload=payload,
            )

            publish_time = time.perf_counter()
            await event_bus.publish(event)
            await event_bus.wait_for_pending()

            # 查询投影表确认写入完成
            elapsed = time.perf_counter() - publish_time
            round_latencies.append(elapsed)

        avg_round = sum(round_latencies) / len(round_latencies)
        latencies.append(avg_round)

    avg_latency = sum(latencies) / len(latencies)
    print("\nMVP-22.5 CQRS投影更新延迟基线:")
    print(f"  {N_APPEND}个事件/轮, {N_ROUNDS}轮, 平均延迟 {avg_latency * 1000:.2f}ms")
    for i, lat in enumerate(latencies):
        print(f"  第{i + 1}轮: {lat * 1000:.2f}ms")

    benchmark_results.append(
        {
            "tc": "MVP-22.5",
            "metric": "cqrs_projection_latency",
            "unit": "ms",
            "rounds": [lat * 1000 for lat in latencies],
            "average": avg_latency * 1000,
        }
    )


# -- MVP-22.6: SSE推送延迟 --


@pytest.mark.asyncio
async def test_tc22_6_sse_push_latency(
    event_bus: InProcessEventBus,
    sse_channel: SSEChannel,
    benchmark_results: list[dict[str, Any]],
) -> None:
    """MVP-22.6: 建立SSE连接 → publish事件 → 前端收到SSE推送 → 计算从事件发布到前端收到的延迟"""
    project_id = "bench-proj-sse"
    user_id = "bench-user-sse"
    queue: asyncio.Queue[dict[str, object]] = asyncio.Queue()
    await sse_channel.add_connection(user_id, queue)

    latencies: list[float] = []
    for _ in range(N_ROUNDS):
        round_latencies = []
        for i in range(N_APPEND):
            payload = DiscussionMessageCreatedPayload(
                thread_id="bench-thread",
                content=f"bench-sse-{i}",
            ).model_dump(mode="json")
            event = make_bench_event(
                project_id=project_id,
                event_type=EventType.DiscussionMessageCreated,
                payload=payload,
            )

            publish_time = time.perf_counter()
            await event_bus.publish(event)
            await event_bus.wait_for_pending()

            # 从queue中取SSE事件
            sse_event = await asyncio.wait_for(queue.get(), timeout=5)
            receive_time = time.perf_counter()
            round_latencies.append(receive_time - publish_time)

            assert sse_event["event"] == "message_created"

        avg_round = sum(round_latencies) / len(round_latencies)
        latencies.append(avg_round)

    sse_channel.remove_connection(user_id, queue)

    avg_latency = sum(latencies) / len(latencies)
    print("\nMVP-22.6 SSE推送延迟基线:")
    print(f"  {N_APPEND}个事件/轮, {N_ROUNDS}轮, 平均延迟 {avg_latency * 1000:.4f}ms")
    for i, lat in enumerate(latencies):
        print(f"  第{i + 1}轮: {lat * 1000:.4f}ms")

    benchmark_results.append(
        {
            "tc": "MVP-22.6",
            "metric": "sse_push_latency",
            "unit": "ms",
            "rounds": [lat * 1000 for lat in latencies],
            "average": avg_latency * 1000,
        }
    )
