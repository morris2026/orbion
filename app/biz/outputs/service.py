"""任务产出审批业务逻辑 — 纯CQRS写端"""

import uuid
from datetime import UTC, datetime
from typing import Any

from app.hub.events.bus import EventBus
from app.hub.events.projections import EventProjectionsProtocol
from app.hub.events.store import EventStoreProtocol
from app.hub.events.types import (
    Event,
    EventType,
    TaskOutputApprovedPayload,
    TaskOutputRevisionRequestedPayload,
)

_MSG_OUTPUT_NOT_FOUND = "产出不存在"
_MSG_ILLEGAL_TRANSITION = "非法状态转换"


class OutputService:
    """任务产出审批——CQRS写端"""

    def __init__(
        self,
        event_store: EventStoreProtocol,
        event_bus: EventBus,
        projections: EventProjectionsProtocol,
    ) -> None:
        self._event_store = event_store
        self._event_bus = event_bus
        self._projections = projections

    async def list_outputs(self, project_id: str, plan_id: str | None = None) -> list[dict[str, Any]]:
        """列出任务产出，可按plan_id过滤"""
        return await self._projections.get_task_outputs(project_id, plan_id)

    async def approve_output(
        self,
        output_id: str,
        feedback: str | None,
        approver_id: str,
        approver_name: str,
        project_id: str,
    ) -> dict[str, Any]:
        """审批产出通过"""
        # Why: 同PlanService——读投影查状态，CQRS最终一致性约束
        output = await self.get_output_by_id(output_id)
        if output is None:
            raise ValueError(_MSG_OUTPUT_NOT_FOUND)
        # 状态机守卫：只有generated可以approve
        if output["status"] != "generated":
            raise ValueError(_MSG_ILLEGAL_TRANSITION)

        payload = TaskOutputApprovedPayload(
            output_id=output_id,
            feedback=feedback,
        )
        event = Event(
            event_id=str(uuid.uuid4()),
            project_id=project_id,
            event_type=EventType.TaskOutputApproved,
            participant_id=approver_id,
            participant_type="human",
            participant_display_name=approver_name,
            payload=payload.model_dump(mode="json"),
            correlation_id=output.get("plan_id", output_id),
            causation_id=output_id,
            created_at=datetime.now(UTC),
        )

        await self._event_store.append(event)
        await self._event_bus.publish(event)

        return {
            "output_id": output_id,
            "status": "approved",
            "feedback": feedback,
        }

    async def request_revision(
        self,
        output_id: str,
        issues: list[str],
        suggestions: list[str],
        requester_id: str,
        requester_name: str,
        project_id: str,
    ) -> dict[str, Any]:
        """要求修改产出"""
        output = await self.get_output_by_id(output_id)
        if output is None:
            raise ValueError(_MSG_OUTPUT_NOT_FOUND)
        # 状态机守卫：只有generated可以request-revision
        if output["status"] != "generated":
            raise ValueError(_MSG_ILLEGAL_TRANSITION)

        task_id = output["task_id"]
        payload = TaskOutputRevisionRequestedPayload(
            output_id=output_id,
            task_id=task_id,
            issues=issues,
            suggestions=suggestions,
        )
        event = Event(
            event_id=str(uuid.uuid4()),
            project_id=project_id,
            event_type=EventType.TaskOutputRevisionRequested,
            participant_id=requester_id,
            participant_type="human",
            participant_display_name=requester_name,
            payload=payload.model_dump(mode="json"),
            correlation_id=output.get("plan_id", output_id),
            causation_id=output_id,
            created_at=datetime.now(UTC),
        )

        await self._event_store.append(event)
        await self._event_bus.publish(event)

        return {
            "output_id": output_id,
            "status": "revision_requested",
            "issues": issues,
            "suggestions": suggestions,
        }

    async def get_output_by_id(self, output_id: str) -> dict[str, Any] | None:
        """按output_id查找产出——路由层需要反查project_id做权限检查"""
        return await self._projections.get_output_by_id(output_id)
