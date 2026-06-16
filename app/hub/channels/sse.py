"""SSEChannel实现——订阅EventBus按用户级推送SSE事件"""

import asyncio
import json
from collections import defaultdict
from typing import Any

from app.biz.projects.read_repo import ProjectReadProtocol
from app.hub.events.bus import EventBus
from app.hub.events.types import (
    DiscussionMessageCreatedPayload,
    DiscussionSummaryGeneratedPayload,
    Event,
    EventType,
    ExecutionPlanApprovedPayload,
    ExecutionPlanProposedPayload,
    ExecutionPlanRejectedPayload,
    MemberAddedPayload,
    ProjectCreatedPayload,
    TaskOutputApprovedPayload,
    TaskOutputGeneratedPayload,
    TaskOutputRevisionRequestedPayload,
)


class SSEChannel:
    """SSE推送Channel实现（用户级连接）。

    维护按user_id分组的asyncio.Queue连接池，订阅EventBus事件，
    根据project_id→在线用户映射路由推送到对应用户的SSE连接。
    新增ProjectCreated订阅：creator通过ProjectCreated投影成为成员，
    不经过MemberAdded事件，需在SSEChannel中更新映射。
    """

    def __init__(self, event_bus: EventBus, project_read: ProjectReadProtocol) -> None:
        self._bus = event_bus
        self._project_read = project_read
        # user_id → 该用户的SSE连接队列列表
        self._connections: dict[str, list[asyncio.Queue[dict[str, Any]]]] = defaultdict(list)
        # user_id → 该用户订阅的project_id集合
        self._user_projects: dict[str, set[str]] = defaultdict(set)
        # project_id → 订阅该项目的在线user_id集合（反向索引，加速路由）
        self._project_users: dict[str, set[str]] = defaultdict(set)
        # 订阅9种业务事件
        self._bus.subscribe(EventType.DiscussionMessageCreated, self._on_message)
        self._bus.subscribe(EventType.DiscussionSummaryGenerated, self._on_summary)
        self._bus.subscribe(EventType.ExecutionPlanProposed, self._on_plan_proposed)
        self._bus.subscribe(EventType.ExecutionPlanApproved, self._on_plan_approved)
        self._bus.subscribe(EventType.ExecutionPlanRejected, self._on_plan_rejected)
        self._bus.subscribe(EventType.TaskOutputGenerated, self._on_output)
        self._bus.subscribe(EventType.TaskOutputApproved, self._on_output_approved)
        self._bus.subscribe(EventType.TaskOutputRevisionRequested, self._on_revision)
        self._bus.subscribe(EventType.MemberAdded, self._on_member_added)
        # 订阅ProjectCreated：creator不经过MemberAdded，需在此更新映射
        self._bus.subscribe(EventType.ProjectCreated, self._on_project_created)

    async def add_connection(self, user_id: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        """前端建立SSE连接时注册Queue，并从读端加载用户所属项目初始化订阅"""
        self._connections[user_id].append(queue)
        # 从读端加载用户参与的项目列表
        projects = await self._project_read.list_projects(user_id)
        project_ids = {p["id"] for p in projects}
        self._user_projects[user_id] = project_ids
        for pid in project_ids:
            self._project_users[pid].add(user_id)

    def remove_connection(self, user_id: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        """前端断开SSE连接时移除Queue"""
        conns = self._connections.get(user_id, [])
        if queue in conns:
            conns.remove(queue)
        if not conns:
            # 该用户无剩余连接，清理映射
            del self._connections[user_id]
            for pid in self._user_projects.pop(user_id, set()):
                users = self._project_users.get(pid, set())
                users.discard(user_id)
                if not users:
                    del self._project_users[pid]

    async def send_event(self, project_id: str, event_type: str, payload: dict[str, Any]) -> None:
        """ChannelAdapter实现：推送SSE事件到project_id下所有在线用户"""
        sse_data = {"event": event_type, "data": json.dumps(payload)}
        for user_id in self._project_users.get(project_id, set()):
            for queue in self._connections.get(user_id, []):
                await queue.put(sse_data)

    async def receive_event(self, external_event: dict[str, Any]) -> dict[str, Any]:
        """SSE是outbound-only通道，MVP不支持inbound"""
        raise NotImplementedError("SSEChannel不支持inbound事件翻译")

    # -- 映射维护 --

    def _add_user_project(self, user_id: str, project_id: str) -> None:
        """将用户加入项目的在线映射（如果用户在线）"""
        if user_id in self._connections:
            self._user_projects[user_id].add(project_id)
            self._project_users[project_id].add(user_id)

    # -- EventBus handler：Event → SSE事件翻译 --

    async def _on_project_created(self, event: Event) -> None:
        """ProjectCreated事件：creator通过投影成为成员，更新在线映射"""
        self._add_user_project(event.participant_id, event.project_id)
        # 也推送member_added SSE事件，让前端知道有新项目可订阅
        payload = ProjectCreatedPayload(**event.payload)
        data = {
            "project_id": event.project_id,
            "participant_id": event.participant_id,
            "participant_type": event.participant_type,
            "participant_display_name": event.participant_display_name,
            "name": payload.name,
            "description": payload.description,
            "created_at": event.created_at.isoformat() if event.created_at else None,
        }
        await self.send_event(event.project_id, "project_created", data)

    async def _on_message(self, event: Event) -> None:
        payload = DiscussionMessageCreatedPayload(**event.payload)
        data = {
            "project_id": event.project_id,
            "message_id": payload.message_id,
            "thread_id": payload.thread_id,
            "participant_id": event.participant_id,
            "participant_type": event.participant_type,
            "participant_display_name": event.participant_display_name,
            "content": payload.content,
            "created_at": event.created_at.isoformat() if event.created_at else None,
        }
        await self.send_event(event.project_id, "message_created", data)

    async def _on_summary(self, event: Event) -> None:
        payload = DiscussionSummaryGeneratedPayload(**event.payload)
        data = {
            "project_id": event.project_id,
            "summary_id": payload.summary_id,
            "thread_id": payload.thread_id,
            "participant_id": event.participant_id,
            "participant_type": event.participant_type,
            "participant_display_name": event.participant_display_name,
            "consensus_points": payload.consensus_points,
            "divergence_points": payload.divergence_points,
            "action_items": payload.action_items,
            "knowledge_references": payload.knowledge_references,
            "created_at": event.created_at.isoformat() if event.created_at else None,
        }
        await self.send_event(event.project_id, "summary_generated", data)

    async def _on_plan_proposed(self, event: Event) -> None:
        payload = ExecutionPlanProposedPayload(**event.payload)
        data = {
            "project_id": event.project_id,
            "plan_id": payload.plan_id,
            "thread_id": payload.thread_id,
            "participant_id": event.participant_id,
            "participant_type": event.participant_type,
            "participant_display_name": event.participant_display_name,
            "tasks": [t.model_dump(mode="json") for t in payload.tasks],
            "created_at": event.created_at.isoformat() if event.created_at else None,
        }
        await self.send_event(event.project_id, "plan_proposed", data)

    async def _on_plan_approved(self, event: Event) -> None:
        payload = ExecutionPlanApprovedPayload(**event.payload)
        data = {
            "project_id": event.project_id,
            "plan_id": payload.plan_id,
            "participant_id": event.participant_id,
            "participant_type": event.participant_type,
            "participant_display_name": event.participant_display_name,
            "approved_tasks": payload.approved_tasks,
            "modifications": payload.modifications,
            "created_at": event.created_at.isoformat() if event.created_at else None,
        }
        await self.send_event(event.project_id, "plan_approved", data)

    async def _on_plan_rejected(self, event: Event) -> None:
        payload = ExecutionPlanRejectedPayload(**event.payload)
        data = {
            "project_id": event.project_id,
            "plan_id": payload.plan_id,
            "participant_id": event.participant_id,
            "participant_type": event.participant_type,
            "participant_display_name": event.participant_display_name,
            "reason": payload.reason,
            "suggestions": payload.suggestions,
            "created_at": event.created_at.isoformat() if event.created_at else None,
        }
        await self.send_event(event.project_id, "plan_rejected", data)

    async def _on_output(self, event: Event) -> None:
        payload = TaskOutputGeneratedPayload(**event.payload)
        data = {
            "project_id": event.project_id,
            "output_id": payload.output_id,
            "task_id": payload.task_id,
            "plan_id": payload.plan_id,
            "participant_id": event.participant_id,
            "participant_type": event.participant_type,
            "participant_display_name": event.participant_display_name,
            "output_type": payload.output_type,
            "content": payload.content,
            "diff": payload.diff,
            "file_paths": payload.file_paths,
            "created_at": event.created_at.isoformat() if event.created_at else None,
        }
        await self.send_event(event.project_id, "output_generated", data)

    async def _on_output_approved(self, event: Event) -> None:
        payload = TaskOutputApprovedPayload(**event.payload)
        data = {
            "project_id": event.project_id,
            "output_id": payload.output_id,
            "participant_id": event.participant_id,
            "participant_type": event.participant_type,
            "participant_display_name": event.participant_display_name,
            "feedback": payload.feedback,
            "created_at": event.created_at.isoformat() if event.created_at else None,
        }
        await self.send_event(event.project_id, "output_approved", data)

    async def _on_revision(self, event: Event) -> None:
        payload = TaskOutputRevisionRequestedPayload(**event.payload)
        data = {
            "project_id": event.project_id,
            "output_id": payload.output_id,
            "task_id": payload.task_id,
            "participant_id": event.participant_id,
            "participant_type": event.participant_type,
            "participant_display_name": event.participant_display_name,
            "issues": payload.issues,
            "suggestions": payload.suggestions,
            "created_at": event.created_at.isoformat() if event.created_at else None,
        }
        await self.send_event(event.project_id, "revision_requested", data)

    async def _on_member_added(self, event: Event) -> None:
        payload = MemberAddedPayload(**event.payload)
        # 更新在线映射：被添加的用户如果在线，将其加入项目的订阅
        self._add_user_project(event.participant_id, event.project_id)
        data = {
            "project_id": event.project_id,
            "participant_id": event.participant_id,
            "participant_type": event.participant_type,
            "participant_display_name": event.participant_display_name,
            "roles": payload.roles,
            "created_at": event.created_at.isoformat() if event.created_at else None,
        }
        await self.send_event(event.project_id, "member_added", data)
