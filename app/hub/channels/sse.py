"""SSEChannel实现——订阅EventBus推送SSE事件"""

import asyncio
import json
from collections import defaultdict
from typing import Any

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
    TaskOutputApprovedPayload,
    TaskOutputGeneratedPayload,
    TaskOutputRevisionRequestedPayload,
)


class SSEChannel:
    """SSE推送Channel实现（ChannelAdapter）。

    订阅EventBus的9种业务事件，维护按project_id分组的asyncio.Queue连接池，
    将Event翻译为SSE格式推送给前端。
    agent_status_changed通过send_event直接调用推送（Agent Runtime触发）。
    """

    def __init__(self, event_bus: EventBus) -> None:
        self._bus = event_bus
        self._connections: dict[str, list[asyncio.Queue[dict[str, Any]]]] = defaultdict(list)
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

    def add_connection(self, project_id: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        """前端建立SSE连接时注册Queue"""
        self._connections[project_id].append(queue)

    def remove_connection(self, project_id: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        """前端断开SSE连接时移除Queue"""
        conns = self._connections.get(project_id, [])
        if queue in conns:
            conns.remove(queue)

    async def send_event(self, project_id: str, event_type: str, payload: dict[str, Any]) -> None:
        """ChannelAdapter实现：推送SSE事件到project_id下所有连接"""
        sse_data = {"event": event_type, "data": json.dumps(payload)}
        for queue in self._connections.get(project_id, []):
            await queue.put(sse_data)

    async def receive_event(self, external_event: dict[str, Any]) -> dict[str, Any]:
        """SSE是outbound-only通道，MVP不支持inbound"""
        raise NotImplementedError("SSEChannel不支持inbound事件翻译")

    # -- EventBus handler：Event → SSE事件翻译 --

    async def _on_message(self, event: Event) -> None:
        payload = DiscussionMessageCreatedPayload(**event.payload)
        data = {
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
        data = {
            "participant_id": event.participant_id,
            "participant_type": event.participant_type,
            "participant_display_name": event.participant_display_name,
            "roles": payload.roles,
            "created_at": event.created_at.isoformat() if event.created_at else None,
        }
        await self.send_event(event.project_id, "member_added", data)
