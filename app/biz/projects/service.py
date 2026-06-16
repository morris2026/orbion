"""项目与成员管理业务逻辑 — 纯CQRS写端"""

import shutil
import uuid
from datetime import UTC, datetime
from typing import Any

from app.biz.projects.read_repo import ProjectReadProtocol
from app.config import Settings
from app.hub.auth.models import User
from app.hub.events.bus import EventBus
from app.hub.events.store import EventStoreProtocol
from app.hub.events.types import Event, EventType, MemberAddedPayload, ProjectCreatedPayload, ProjectDeletedPayload
from app.hub.permissions.bitmask import HumanPermission
from app.hub.permissions.compute import compute_permissions

_MSG_MEMBER_EXISTS = "成员已在项目中"
_MSG_PROJECT_EXISTS = "项目名称已存在"


class ProjectService:
    def __init__(
        self,
        event_store: EventStoreProtocol,
        event_bus: EventBus,
        read_repo: ProjectReadProtocol,
        settings: Settings | None = None,
    ) -> None:
        self._event_store = event_store
        self._event_bus = event_bus
        self._read_repo = read_repo
        self._settings = settings

    async def create_project(self, name: str, description: str | None, creator: User) -> dict[str, Any]:
        """创建项目+默认线程，创建者自动成为Owner — 从命令输入构造响应，不读投影表"""
        # best-effort前置检查（真实去重由DB UNIQUE兜底）
        if await self._read_repo.check_project_name_exists(name):
            raise ValueError(_MSG_PROJECT_EXISTS)

        project_id = str(uuid.uuid4())
        thread_id = str(uuid.uuid4())
        now = datetime.now(UTC)

        payload = ProjectCreatedPayload(
            name=name,
            description=description,
            default_thread_id=thread_id,
            default_thread_title=name,
        )
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

        if self._settings:
            self._init_project_dirs(self._settings, project_id)

        # 写入event_log + 发布到EventBus（等待投影处理完成，确保后续查询可见）
        await self._event_store.append(event)
        await self._event_bus.publish(event)
        await self._event_bus.wait_for_pending()

        # 从命令输入构造响应（CQRS写端不从读端取数据）
        return {
            "id": project_id,
            "name": name,
            "description": description,
            "tenant_id": "default",
            "default_thread_id": thread_id,
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

    async def delete_project(self, project_id: str, user_id: str) -> bool:
        """删除项目：权限校验 → 审计事件 → 级联删除投影表"""
        roles = await self._read_repo.get_member_roles(project_id, user_id)
        if roles is None:
            return False
        if not compute_permissions(roles, HumanPermission.DELETE_PROJECT):
            raise PermissionError("Insufficient permissions")

        project = await self._read_repo.get_project(project_id, user_id)
        if project is None:
            return False

        now = datetime.now(UTC)
        payload = ProjectDeletedPayload(name=project["name"])
        event = Event(
            event_id=str(uuid.uuid4()),
            project_id=project_id,
            event_type=EventType.ProjectDeleted,
            participant_id=user_id,
            participant_type="human",
            participant_display_name="",
            payload=payload.model_dump(mode="json"),
            correlation_id=project_id,
            created_at=now,
        )
        await self._event_store.append(event)
        await self._event_bus.publish(event)

        if self._settings:
            self._cleanup_project_dirs(self._settings, project_id)

        return await self._read_repo.delete_project(project_id)

    @staticmethod
    def _init_project_dirs(settings: Settings, project_id: str) -> None:
        """创建项目文件系统目录：project_dir + memory.md + repo/"""
        project_dir = settings.project_dir(project_id)
        project_dir.mkdir(parents=True, exist_ok=True)
        mem_path = settings.project_memory_path(project_id)
        if not mem_path.exists():
            mem_path.write_text("", encoding="utf-8")
        repo_dir = project_dir / "repo"
        repo_dir.mkdir(exist_ok=True)

    @staticmethod
    def _cleanup_project_dirs(settings: Settings, project_id: str) -> None:
        """删除项目文件系统目录（含 git 仓库和 Agent 记忆）"""
        project_dir = settings.project_dir(project_id)
        if project_dir.exists():
            shutil.rmtree(project_dir, ignore_errors=True)
