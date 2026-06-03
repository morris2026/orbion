"""SSE推送与事件流端点集成测试：TC-11.1–TC-11.6"""

import asyncio
import json
import uuid
from collections.abc import AsyncGenerator, MutableMapping
from typing import Any, Literal

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient

from app.biz.projects.read_repo import load_project_read_impl
from app.biz.projects.service import ProjectService
from app.biz.threads.read_repo import load_thread_read_impl
from app.biz.threads.service import ThreadService
from app.config import get_settings
from app.hub.auth.repository import UserRepositoryProvider, load_user_repo_provider
from app.hub.auth.service import create_access_token, hash_password
from app.hub.channels.sse import SSEChannel
from app.hub.events.bus import InProcessEventBus
from app.hub.events.projections import load_projections_impl
from app.hub.events.store import load_store_impl
from app.hub.events.types import (
    DiscussionMessageCreatedPayload,
    DiscussionSummaryGeneratedPayload,
    Event,
    EventType,
    ExecutionPlanApprovedPayload,
    ExecutionPlanProposedPayload,
    ExecutionPlanRejectedPayload,
    MemberAddedPayload,
    PlanTaskItem,
    TaskOutputApprovedPayload,
    TaskOutputGeneratedPayload,
    TaskOutputRevisionRequestedPayload,
)
from app.main import app

settings = get_settings()


# -- SSEChannel直接测试fixture --


@pytest.fixture
async def event_bus() -> InProcessEventBus:
    return InProcessEventBus()


@pytest.fixture
async def sse_channel(event_bus: InProcessEventBus) -> SSEChannel:
    return SSEChannel(event_bus)


# -- HTTP端点测试fixture --


@pytest.fixture
async def user_repo_provider() -> AsyncGenerator[UserRepositoryProvider, None]:
    provider_cls = load_user_repo_provider(settings.user_repo)
    provider = provider_cls()
    await provider.connect()
    yield provider
    await provider.close()


@pytest.fixture
async def http_client(
    event_bus: InProcessEventBus,
    sse_channel: SSEChannel,
    user_repo_provider: UserRepositoryProvider,
) -> AsyncGenerator[AsyncClient, None]:
    """httpx AsyncClient，初始化app.state（含SSEChannel）"""
    store_cls = load_store_impl(settings.event_store)
    event_store = store_cls()
    await event_store.connect()

    proj_cls = load_projections_impl(settings.event_projections)
    projections = proj_cls(event_bus)
    await projections.connect()

    read_cls = load_project_read_impl(settings.project_read)
    project_read = read_cls()
    await project_read.connect()

    thread_read_cls = load_thread_read_impl(settings.thread_read)
    thread_read = thread_read_cls()
    await thread_read.connect()

    project_service = ProjectService(event_store, event_bus, project_read)
    thread_service = ThreadService(event_store, event_bus, thread_read, project_read)

    app.state.event_store = event_store
    app.state.event_bus = event_bus
    app.state.event_projections = projections
    app.state.project_read = project_read
    app.state.project_service = project_service
    app.state.thread_read = thread_read
    app.state.thread_service = thread_service
    app.state.user_repo_provider = user_repo_provider
    app.state.sse_channel = sse_channel

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    await projections.close()
    await thread_read.close()
    await project_read.close()
    await event_store.close()


# -- helpers --


async def _create_user(provider: UserRepositoryProvider, username: str, is_admin: bool = False) -> dict[str, Any]:
    """创建active用户并返回{id, token, ...}"""
    async with provider.scoped() as repo:
        user = await repo.create_user(username, hash_password("testpass123"), username.capitalize(), "active", is_admin)
    token = create_access_token(
        user_id=user.id,
        username=user.username,
        display_name=user.display_name,
        is_admin=user.is_admin,
        settings=settings,
    )
    return {"id": user.id, "token": token, "username": user.username, "display_name": user.display_name}


async def _create_project(client: AsyncClient, token: str, name: str = "TestProject") -> dict[str, Any]:
    """创建项目并返回完整项目数据"""
    resp = await client.post(
        "/projects",
        json={"name": name, "description": "test"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    return dict(resp.json())


def _make_event(
    project_id: str,
    event_type: str | EventType,
    participant_id: str = "user-1",
    participant_type: Literal["human", "agent"] = "human",
    participant_display_name: str = "TestUser",
    payload: dict[str, Any] = {},
    correlation_id: str | None = None,
) -> Event:
    """构造Event对象的快捷函数"""
    return Event(
        event_id=str(uuid.uuid4()),
        project_id=project_id,
        event_type=str(event_type),
        participant_id=participant_id,
        participant_type=participant_type,
        participant_display_name=participant_display_name,
        payload=payload,
        correlation_id=correlation_id or str(uuid.uuid4()),
    )


# -- TC-11.2: DiscussionMessageCreated→SSE推送message_created --


async def test_tc11_2_message_created_push(event_bus: InProcessEventBus, sse_channel: SSEChannel) -> None:
    """TC-11.2: DiscussionMessageCreated→SSE推送message_created，data含消息内容"""
    project_id = "proj-test-2"
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    sse_channel.add_connection(project_id, queue)

    payload = DiscussionMessageCreatedPayload(
        thread_id="thread-1", content="hello world", request_summary=False, message_id="msg-1"
    )
    event = _make_event(
        project_id=project_id,
        event_type=EventType.DiscussionMessageCreated,
        payload=payload.model_dump(mode="json"),
    )
    await event_bus.publish(event)
    await event_bus.wait_for_pending()

    sse_event = await asyncio.wait_for(queue.get(), timeout=5)
    assert sse_event["event"] == "message_created"
    data = json.loads(sse_event["data"]) if isinstance(sse_event["data"], str) else sse_event["data"]
    assert data["content"] == "hello world"
    assert data["participant_id"] == "user-1"

    sse_channel.remove_connection(project_id, queue)


# -- TC-11.3: DiscussionSummaryGenerated→SSE推送summary_generated --


async def test_tc11_3_summary_generated_push(event_bus: InProcessEventBus, sse_channel: SSEChannel) -> None:
    """TC-11.3: DiscussionSummaryGenerated→SSE推送summary_generated"""
    project_id = "proj-test-3"
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    sse_channel.add_connection(project_id, queue)

    payload = DiscussionSummaryGeneratedPayload(
        thread_id="thread-1",
        summary_id="summary-1",
        consensus_points=["共识1"],
        divergence_points=["分歧1"],
        action_items=["行动1"],
        knowledge_references=[],
    )
    event = _make_event(
        project_id=project_id,
        event_type=EventType.DiscussionSummaryGenerated,
        participant_id="agent-summary-1",
        participant_type="agent",
        participant_display_name="Summary Agent",
        payload=payload.model_dump(mode="json"),
    )
    await event_bus.publish(event)
    await event_bus.wait_for_pending()

    sse_event = await asyncio.wait_for(queue.get(), timeout=5)
    assert sse_event["event"] == "summary_generated"
    data = json.loads(sse_event["data"]) if isinstance(sse_event["data"], str) else sse_event["data"]
    assert data["consensus_points"] == ["共识1"]

    sse_channel.remove_connection(project_id, queue)


# -- TC-11.4: 所有9种业务事件+agent_status_changed通过SSE推送 --


async def test_tc11_4_all_event_types_push(event_bus: InProcessEventBus, sse_channel: SSEChannel) -> None:
    """TC-11.4: 所有9种业务事件+agent_status_changed通过SSE推送（共10种SSE event类型）"""
    project_id = "proj-test-4"
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    sse_channel.add_connection(project_id, queue)

    # 9种业务事件→对应SSE event名
    business_events: list[tuple[str | EventType, str, dict[str, Any]]] = [
        (
            EventType.DiscussionMessageCreated,
            "message_created",
            DiscussionMessageCreatedPayload(thread_id="t1", content="msg", message_id="m1").model_dump(mode="json"),
        ),
        (
            EventType.DiscussionSummaryGenerated,
            "summary_generated",
            DiscussionSummaryGeneratedPayload(
                thread_id="t1",
                summary_id="s1",
                consensus_points=[],
                divergence_points=[],
                action_items=[],
                knowledge_references=[],
            ).model_dump(mode="json"),
        ),
        (
            EventType.ExecutionPlanProposed,
            "plan_proposed",
            ExecutionPlanProposedPayload(
                plan_id="p1",
                thread_id="t1",
                tasks=[PlanTaskItem(task_id="task1", type="code", description="do stuff", priority="high")],
            ).model_dump(mode="json"),
        ),
        (
            EventType.ExecutionPlanApproved,
            "plan_approved",
            ExecutionPlanApprovedPayload(plan_id="p1", approved_tasks=["task1"]).model_dump(mode="json"),
        ),
        (
            EventType.ExecutionPlanRejected,
            "plan_rejected",
            ExecutionPlanRejectedPayload(plan_id="p1", reason="bad", suggestions=["fix"]).model_dump(mode="json"),
        ),
        (
            EventType.TaskOutputGenerated,
            "output_generated",
            TaskOutputGeneratedPayload(
                task_id="task1",
                plan_id="p1",
                output_id="o1",
                output_type="code",
                content="code",
                diff="diff",
                file_paths=["f.py"],
            ).model_dump(mode="json"),
        ),
        (
            EventType.TaskOutputApproved,
            "output_approved",
            TaskOutputApprovedPayload(output_id="o1", feedback="good").model_dump(mode="json"),
        ),
        (
            EventType.TaskOutputRevisionRequested,
            "revision_requested",
            TaskOutputRevisionRequestedPayload(
                output_id="o1", task_id="task1", issues=["i1"], suggestions=["s1"]
            ).model_dump(mode="json"),
        ),
        (EventType.MemberAdded, "member_added", MemberAddedPayload(roles=["member"]).model_dump(mode="json")),
    ]

    # 发布9种业务事件到EventBus
    for event_type, _sse_name, payload_dict in business_events:
        event = _make_event(project_id=project_id, event_type=event_type, payload=payload_dict)
        await event_bus.publish(event)

    await event_bus.wait_for_pending()

    # 直接调用send_event推送agent_status_changed
    await sse_channel.send_event(
        project_id,
        "agent_status_changed",
        {
            "agent_id": "agent-1",
            "status": "running",
            "current_task": "task-1",
        },
    )

    # 收集所有10种SSE event类型
    received_types: set[str] = set()
    for _ in range(10):
        sse_event = await asyncio.wait_for(queue.get(), timeout=5)
        received_types.add(sse_event["event"])

    expected_types = {
        "message_created",
        "summary_generated",
        "plan_proposed",
        "plan_approved",
        "plan_rejected",
        "output_generated",
        "output_approved",
        "revision_requested",
        "member_added",
        "agent_status_changed",
    }
    assert received_types == expected_types

    sse_channel.remove_connection(project_id, queue)


# -- TC-11.6: project_id过滤 --


async def test_tc11_6_project_id_filter(event_bus: InProcessEventBus, sse_channel: SSEChannel) -> None:
    """TC-11.6: project_id过滤——订阅proj-A的SSE不收到proj-B的事件"""
    queue_a: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    queue_b: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    sse_channel.add_connection("proj-A", queue_a)
    sse_channel.add_connection("proj-B", queue_b)

    # 在proj-B发布DiscussionMessageCreated
    payload = DiscussionMessageCreatedPayload(thread_id="thread-B", content="hello from B", message_id="msg-B")
    event = _make_event(
        project_id="proj-B",
        event_type=EventType.DiscussionMessageCreated,
        payload=payload.model_dump(mode="json"),
    )
    await event_bus.publish(event)
    await event_bus.wait_for_pending()

    # proj-B应收到事件
    sse_event_b = await asyncio.wait_for(queue_b.get(), timeout=5)
    assert sse_event_b["event"] == "message_created"

    # proj-A不应收到proj-B的事件
    assert queue_a.empty()

    sse_channel.remove_connection("proj-A", queue_a)
    sse_channel.remove_connection("proj-B", queue_b)


# -- TC-11.1: 建立SSE长连接 + 项目成员授权 --


async def test_tc11_1_sse_connection(
    http_client: AsyncClient,
    event_bus: InProcessEventBus,
    user_repo_provider: UserRepositoryProvider,
    db_conn: asyncpg.Connection,
) -> None:
    """TC-11.1: 建立SSE长连接——Content-Type: text/event-stream + 项目成员授权检查

    httpx ASGITransport不支持SSE流式响应，http_client fixture初始化app.state后用ASGI直接调用。
    """
    user = await _create_user(user_repo_provider, "sseuser1", is_admin=True)
    project = await _create_project(http_client, user["token"])
    # 等待投影写入project_members，否则成员检查会403
    await event_bus.wait_for_pending()

    # 直接ASGI调用——绕过httpx以支持SSE流式响应
    token = user["token"]
    query = f"project_id={project['id']}&token={token}"
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/events/stream",
        "raw_path": b"/events/stream",
        "query_string": query.encode(),
        "root_path": "",
        "headers": [],
        "server": ("testserver", 80),
        "client": ("testclient", 50000),
    }

    received_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    send_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    async def receive() -> dict[str, Any]:
        return await received_queue.get()

    async def send(message: MutableMapping[str, Any]) -> None:
        await send_queue.put(dict(message))

    task = asyncio.create_task(app(scope, receive, send))

    response_start = await asyncio.wait_for(send_queue.get(), timeout=5)
    assert response_start["type"] == "http.response.start"
    assert response_start["status"] == 200
    headers_dict = {k.decode(): v.decode() for k, v in response_start.get("headers", [])}
    assert "text/event-stream" in headers_dict.get("content-type", "")

    # 发送disconnect关闭SSE generator
    await received_queue.put({"type": "http.disconnect"})
    try:
        await asyncio.wait_for(task, timeout=5)
    except TimeoutError:
        task.cancel()


# -- TC-11.5: 无JWT→401 --


async def test_tc11_5_no_jwt_rejected(http_client: AsyncClient) -> None:
    """TC-11.5: 无JWT→连接拒绝，返回401"""
    response = await http_client.get("/events/stream?project_id=some-project")
    assert response.status_code == 401


# -- TC-11.5b: 非项目成员→403 --


async def test_tc11_5b_non_member_rejected(
    http_client: AsyncClient,
    event_bus: InProcessEventBus,
    user_repo_provider: UserRepositoryProvider,
    db_conn: asyncpg.Connection,
) -> None:
    """TC-11.5b: 非项目成员订阅项目SSE流→返回403"""
    admin = await _create_user(user_repo_provider, "sseadmin", is_admin=True)
    project = await _create_project(http_client, admin["token"])
    await event_bus.wait_for_pending()
    # 创建非成员用户
    outsider = await _create_user(user_repo_provider, "outsider1", is_admin=False)
    # outsider尝试订阅admin的项目SSE流
    response = await http_client.get(
        f"/events/stream?project_id={project['id']}",
        headers={"Authorization": f"Bearer {outsider['token']}"},
    )
    assert response.status_code == 403
