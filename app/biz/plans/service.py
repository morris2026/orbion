"""执行计划审批业务逻辑 — 纯CQRS写端"""

import uuid
from datetime import UTC, datetime
from typing import Any

from app.hub.events.bus import EventBus
from app.hub.events.projections import EventProjectionsProtocol
from app.hub.events.store import EventStoreProtocol
from app.hub.events.types import (
    Event,
    EventType,
    ExecutionPlanApprovedPayload,
    ExecutionPlanRejectedPayload,
)

_MSG_PLAN_NOT_FOUND = "计划不存在"
_MSG_ILLEGAL_TRANSITION = "非法状态转换"


class PlanService:
    """执行计划审批——CQRS写端"""

    def __init__(
        self,
        event_store: EventStoreProtocol,
        event_bus: EventBus,
        projections: EventProjectionsProtocol,
    ) -> None:
        self._event_store = event_store
        self._event_bus = event_bus
        self._projections = projections

    async def list_plans(
        self, project_id: str, thread_id: str | None = None, status: str | None = None
    ) -> list[dict[str, Any]]:
        """列出执行计划，可按thread_id和status过滤"""
        return await self._projections.get_execution_plans(project_id, thread_id, status)

    async def approve_plan(
        self,
        plan_id: str,
        approved_tasks: list[str],
        modifications: dict[str, dict[str, Any]] | None,
        approver_id: str,
        approver_name: str,
        project_id: str,
    ) -> dict[str, Any]:
        """审批执行计划——部分审批支持"""
        # Why: 读投影查计划状态——CQRS最终一致性下，若plan刚被proposed但投影尚未更新，
        # get_plan_by_id可能返回None导致404；Phase 2可从EventStore交叉检查plan是否真实存在
        plan = await self.get_plan_by_id(plan_id)
        if plan is None:
            raise ValueError(_MSG_PLAN_NOT_FOUND)
        # 状态机守卫：只有proposed可以approve
        if plan["status"] != "proposed":
            raise ValueError(_MSG_ILLEGAL_TRANSITION)

        # 发布ExecutionPlanApproved事件
        payload = ExecutionPlanApprovedPayload(
            plan_id=plan_id,
            approved_tasks=approved_tasks,
            modifications=modifications,
        )
        event = Event(
            event_id=str(uuid.uuid4()),
            project_id=project_id,
            event_type=EventType.ExecutionPlanApproved,
            participant_id=approver_id,
            participant_type="human",
            participant_display_name=approver_name,
            payload=payload.model_dump(mode="json"),
            correlation_id=plan.get("correlation_id", plan_id),
            causation_id=plan_id,
            created_at=datetime.now(UTC),
        )

        await self._event_store.append(event)
        await self._event_bus.publish(event)

        return {
            "plan_id": plan_id,
            "status": "approved",
            "approved_tasks": approved_tasks,
            "modifications": modifications,
        }

    async def reject_plan(
        self,
        plan_id: str,
        reason: str,
        suggestions: list[str],
        rejecter_id: str,
        rejecter_name: str,
        project_id: str,
    ) -> dict[str, Any]:
        """拒绝执行计划——含修改意见"""
        # Why: 同approve_plan——读投影查状态，CQRS最终一致性约束
        plan = await self.get_plan_by_id(plan_id)
        if plan is None:
            raise ValueError(_MSG_PLAN_NOT_FOUND)
        # 状态机守卫：只有proposed可以reject
        if plan["status"] != "proposed":
            raise ValueError(_MSG_ILLEGAL_TRANSITION)

        # 发布ExecutionPlanRejected事件
        payload = ExecutionPlanRejectedPayload(
            plan_id=plan_id,
            reason=reason,
            suggestions=suggestions,
        )
        event = Event(
            event_id=str(uuid.uuid4()),
            project_id=project_id,
            event_type=EventType.ExecutionPlanRejected,
            participant_id=rejecter_id,
            participant_type="human",
            participant_display_name=rejecter_name,
            payload=payload.model_dump(mode="json"),
            correlation_id=plan.get("correlation_id", plan_id),
            causation_id=plan_id,
            created_at=datetime.now(UTC),
        )

        await self._event_store.append(event)
        await self._event_bus.publish(event)

        return {
            "plan_id": plan_id,
            "status": "rejected",
            "reason": reason,
            "suggestions": suggestions,
        }

    async def get_plan_by_id(self, plan_id: str) -> dict[str, Any] | None:
        """按plan_id查找计划——路由层需要反查project_id做权限检查"""
        return await self._projections.get_plan_by_id(plan_id)
