"""项目与成员管理业务逻辑 — 纯CQRS写端"""

import uuid
from datetime import UTC, datetime
from typing import Any

from app.biz.projects.read_repo import ProjectReadProtocol
from app.hub.auth.models import User
from app.hub.events.bus import EventBus
from app.hub.events.store import EventStoreProtocol
from app.hub.events.types import Event, EventType, MemberAddedPayload, ProjectCreatedPayload

_MSG_MEMBER_EXISTS = "成员已在项目中"


class ProjectService:
    def __init__(self, event_store: EventStoreProtocol, event_bus: EventBus, read_repo: ProjectReadProtocol) -> None:
        self._event_store = event_store
        self._event_bus = event_bus
        self._read_repo = read_repo

    async def create_project(self, name: str, description: str | None, creator: User) -> dict[str, Any]:
        """创建项目，创建者自动成为Owner — 从命令输入构造响应，不读投影表"""
        project_id = str(uuid.uuid4())
        now = datetime.now(UTC)

        payload = ProjectCreatedPayload(name=name, description=description)
        event = Event(
            event_id=str(uuid.uuid4()),
            project_id=project_id,
            event_type=EventType.ProjectCreated,
            participant_id=creator.id,
            participant_type="human",
            participant_display_name=creator.display_name,
            payload=payload.model_dump(mode="json"),
            correlation_id=project_id,
            created_at=now,
        )

        # 写入event_log + 发布到EventBus（fire-and-forget，投影最终一致）
        await self._event_store.append(event)
        await self._event_bus.publish(event)

        # 从命令输入构造响应（CQRS写端不从读端取数据）
        return {
            "id": project_id,
            "name": name,
            "description": description,
            "tenant_id": "default",
            "created_at": now,
        }

    async def list_projects(self, user_id: str) -> list[dict[str, Any]]:
        """列出用户参与的项目，含role字段"""
        return await self._read_repo.list_projects(user_id)

    async def get_project(self, project_id: str, user_id: str) -> dict[str, Any] | None:
        """获取项目详情，仅成员可访问"""
        return await self._read_repo.get_project(project_id, user_id)

    async def add_member(
        self, project_id: str, user_id: str, role: str, display_name: str, actor_id: str
    ) -> dict[str, Any]:
        """添加成员到项目 — 从命令输入构造响应，不读投影表"""
        # best-effort前置检查（最终一致性下不保证实时准确，真实去重由投影handler ON CONFLICT保证）
        if await self._read_repo.check_member_exists(project_id, user_id):
            raise ValueError(_MSG_MEMBER_EXISTS)

        payload = MemberAddedPayload(roles=[role])
        event = Event(
            event_id=str(uuid.uuid4()),
            project_id=project_id,
            event_type=EventType.MemberAdded,
            participant_id=user_id,
            participant_type="human",
            participant_display_name=display_name,
            payload=payload.model_dump(mode="json"),
            correlation_id=str(uuid.uuid4()),
        )

        await self._event_store.append(event)
        await self._event_bus.publish(event)

        # 从命令输入构造响应
        return {
            "participant_id": user_id,
            "project_id": project_id,
            "type": "human",
            "display_name": display_name,
            "role": role,
        }

    async def get_member_roles(self, project_id: str, user_id: str) -> int | None:
        """查询用户在项目中的roles bitmask"""
        return await self._read_repo.get_member_roles(project_id, user_id)

    async def list_members(self, project_id: str) -> list[dict[str, Any]]:
        """列出项目所有成员"""
        return await self._read_repo.list_members(project_id)
