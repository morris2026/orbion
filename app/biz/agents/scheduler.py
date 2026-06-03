"""AgentScheduler——事件调度器，订阅EventBus路由到AgentRuntime"""

from app.biz.agents.runtime import AgentRuntime
from app.hub.events.bus import EventBus
from app.hub.events.types import Event, EventType

THRESHOLD_DEFAULT = 10


class AgentScheduler:
    """事件→Agent调度器。订阅EventBus路由到对应Agent的runtime.dispatch()"""

    def __init__(self, event_bus: EventBus, runtime: AgentRuntime) -> None:
        self._bus = event_bus
        self._runtime = runtime
        # 线程消息计数器（阈值触发用）
        self._message_counts: dict[str, int] = {}
        # 注册事件订阅
        self._sub_ids: list[str] = [
            self._bus.subscribe(EventType.DiscussionMessageCreated, self._on_message_created),
            self._bus.subscribe(EventType.DiscussionSummaryGenerated, self._on_summary_generated),
            self._bus.subscribe(EventType.ExecutionPlanApproved, self._on_plan_approved),
            self._bus.subscribe(EventType.TaskOutputRevisionRequested, self._on_revision_requested),
        ]

    async def _on_message_created(self, event: Event) -> None:
        """讨论消息→检查是否触发总结Agent"""
        if not self._runtime.has_agent(event.project_id, "summary"):
            return
        payload = event.payload
        thread_id = payload.get("thread_id", "")
        # request_summary=true → 立即触发
        if payload.get("request_summary", False):
            await self._runtime.dispatch(event.project_id, "summary", event)
            self._message_counts.pop(thread_id, None)
            return
        # 阈值触发：累积消息数达到THRESHOLD_DEFAULT
        self._message_counts[thread_id] = self._message_counts.get(thread_id, 0) + 1
        if self._message_counts[thread_id] >= THRESHOLD_DEFAULT:
            await self._runtime.dispatch(event.project_id, "summary", event)
            self._message_counts.pop(thread_id, None)

    async def _on_summary_generated(self, event: Event) -> None:
        """讨论摘要→触发分解Agent"""
        if self._runtime.has_agent(event.project_id, "decompose"):
            await self._runtime.dispatch(event.project_id, "decompose", event)

    async def _on_plan_approved(self, event: Event) -> None:
        """审批通过→触发执行Agent"""
        if self._runtime.has_agent(event.project_id, "execute"):
            await self._runtime.dispatch(event.project_id, "execute", event)

    async def _on_revision_requested(self, event: Event) -> None:
        """修改要求→触发执行Agent重新生成"""
        if self._runtime.has_agent(event.project_id, "execute"):
            await self._runtime.dispatch(event.project_id, "execute", event)

    def close(self) -> None:
        """取消EventBus订阅，用于应用关闭清理"""
        for sub_id in self._sub_ids:
            self._bus.unsubscribe(sub_id)
        self._sub_ids.clear()
