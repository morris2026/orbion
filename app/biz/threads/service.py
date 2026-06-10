"""线程与消息业务逻辑 — 纯CQRS写端"""

import uuid
from datetime import UTC, datetime
from typing import Any

from app.biz.projects.read_repo import ProjectReadProtocol
from app.biz.threads.read_repo import ThreadReadProtocol
from app.hub.auth.models import User
from app.hub.events.bus import EventBus
from app.hub.events.store import EventStoreProtocol
from app.hub.events.types import DiscussionMessageCreatedPayload, Event, EventType

_MSG_THREAD_TITLE_EXISTS = "同项目下线程标题已存在"


class ThreadService:
    def __init__(
        self,
        event_store: EventStoreProtocol,
        event_bus: EventBus,
        thread_read: ThreadReadProtocol,
        project_read: ProjectReadProtocol,
    ) -> None:
        self._event_store = event_store
        self._event_bus = event_bus
        self._thread_read = thread_read
        self._project_read = project_read

    async def create_thread(self, project_id: str, title: str, type: str, creator: User) -> dict[str, Any]:
        """创建线程 — 直接写入threads表 + 发布DiscussionMessageCreated事件作为首条消息"""
        # best-effort前置检查（真实去重由DB UNIQUE兜底）
        if await self._thread_read.check_thread_title_exists(project_id, title):
            raise ValueError(_MSG_THREAD_TITLE_EXISTS)
        thread_id = str(uuid.uuid4())
        now = datetime.now(UTC)

        # CQRS写端：直接写入threads表行（thread_messages FK依赖threads表）
        await self._thread_read.insert_thread(thread_id, project_id, title, type, creator.id)

        # 线程创建消息以标题作为首条内容 — 设计文档3.1要求创建线程同时发布DiscussionMessageCreated事件，
        # 需要有content（MessageCreate min_length=1），标题是线程主题的自然表达
        message_id = str(uuid.uuid4())
        payload = DiscussionMessageCreatedPayload(
            thread_id=thread_id,
            content=title,
            request_summary=False,
            message_id=message_id,
        )

        event = Event(
            event_id=str(uuid.uuid4()),
            project_id=project_id,
            event_type=EventType.DiscussionMessageCreated,
            participant_id=creator.id,
            participant_type="human",
            participant_display_name=creator.display_name,
            payload=payload.model_dump(mode="json"),
            correlation_id=thread_id,
            created_at=now,
        )

        await self._event_store.append(event)
        await self._event_bus.publish(event)

        # 从命令输入构造响应
        return {
            "id": thread_id,
            "project_id": project_id,
            "title": title,
            "status": "active",
            "type": type,
            "created_at": now,
        }

    async def send_message(self, thread_id: str, content: str, request_summary: bool, user: User) -> dict[str, Any]:
        """发送消息 — 构造DiscussionMessageCreated事件 + append + publish"""
        # 查询thread获取project_id
        project_id = await self._thread_read.get_thread_project_id(thread_id)
        if project_id is None:
            raise ValueError(f"Thread {thread_id} not found")

        message_id = str(uuid.uuid4())
        payload = DiscussionMessageCreatedPayload(
            thread_id=thread_id,
            content=content,
            request_summary=request_summary,
            message_id=message_id,
        )

        event = Event(
            event_id=str(uuid.uuid4()),
            project_id=project_id,
            event_type=EventType.DiscussionMessageCreated,
            participant_id=user.id,
            participant_type="human",
            participant_display_name=user.display_name,
            payload=payload.model_dump(mode="json"),
            correlation_id=thread_id,
        )

        await self._event_store.append(event)
        await self._event_bus.publish(event)

        # 从命令输入构造响应
        return {
            "id": message_id,
            "thread_id": thread_id,
            "participant_id": user.id,
            "participant_type": "human",
            "display_name": user.display_name,
            "content": content,
            "event_type": "DiscussionMessageCreated",
            "created_at": datetime.now(UTC),
        }

    async def list_threads(self, project_id: str) -> list[dict[str, Any]]:
        """线程列表含聚合字段"""
        return await self._thread_read.list_threads(project_id)

    async def list_messages(self, thread_id: str, before: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        """消息列表游标分页"""
        return await self._thread_read.get_messages(thread_id, before, limit)

    async def get_member_roles(self, project_id: str, user_id: str) -> int | None:
        """查询用户在项目中的roles bitmask — 委托ProjectReadProtocol"""
        return await self._project_read.get_member_roles(project_id, user_id)

    async def check_thread_in_project(self, thread_id: str, project_id: str) -> bool:
        """验证线程属于指定项目"""
        return await self._thread_read.check_thread_in_project(thread_id, project_id)

    async def check_member_exists(self, project_id: str, user_id: str) -> bool:
        """检查用户是否为项目成员"""
        return await self._thread_read.check_member_exists(project_id, user_id)

    async def get_thread_project_id(self, thread_id: str) -> str | None:
        """通过thread_id查找project_id — 消息端点路径不含project_id"""
        return await self._thread_read.get_thread_project_id(thread_id)
