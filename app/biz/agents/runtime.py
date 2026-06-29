"""AgentRuntime——Agent生命周期管理（状态机、并发守卫、dispatch）"""

import json
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from app.biz.agents.adapters._legacy.base import EventSummary, ModelAdapter, ModelOutput, PromptInput
from app.biz.agents.declarations import AgentDeclaration
from app.biz.agents.memory import AgentMemory
from app.hub.events.bus import EventBus
from app.hub.events.store import EventStoreProtocol
from app.hub.events.types import Event


class AgentState:
    """单个Agent的运行时状态"""

    def __init__(self, declaration: AgentDeclaration) -> None:
        self.declaration = declaration
        self.status: str = "idle"
        self.current_task: str | None = None
        self.completed_count: int = 0
        self.error_count: int = 0
        self.last_execution_at: datetime | None = None
        self.last_error: str | None = None


class AgentRuntime:
    """Agent生命周期管理和调度执行"""

    def __init__(
        self,
        event_bus: EventBus,
        event_store: EventStoreProtocol,
        adapter: ModelAdapter,
        memory: AgentMemory | None = None,
    ) -> None:
        self._bus = event_bus
        self._store = event_store
        self._adapter = adapter
        self._memory = memory
        # project_id → agent_type → AgentState
        self._agents: dict[str, dict[str, AgentState]] = defaultdict(dict)

    def register(self, project_id: str, declaration: AgentDeclaration) -> None:
        """注册Agent声明到指定项目"""
        self._agents[project_id][declaration.agent_type] = AgentState(declaration)

    def has_agent(self, project_id: str, agent_type: str) -> bool:
        """检查项目是否注册了指定类型的Agent"""
        return agent_type in self._agents.get(project_id, {})

    async def dispatch(self, project_id: str, agent_type: str, event: Event) -> None:
        """调度Agent处理事件：状态转换→执行→产出→回到idle/error"""
        project_agents = self._agents.get(project_id, {})
        state = project_agents.get(agent_type)
        if state is None:
            return
        # 并发守卫：running状态不接受新任务
        # Why: 当前dispatch是同步await（串行执行），字符串状态检查已足够；
        # 若未来改为asyncio.create_task并发dispatch，需替换为asyncio.Lock
        if state.status == "running":
            return

        # IDLE/ERROR → RUNNING
        state.status = "running"
        state.current_task = event.event_id

        try:
            # 组装prompt + 调用adapter
            prompt = await self._assemble_prompt(state.declaration, event)
            output = await self._adapter.complete(prompt)
            # 产出完成 → IDLE
            state.status = "idle"
            state.completed_count += 1
            state.last_execution_at = datetime.now(UTC)
            state.current_task = None
            state.last_error = None

            # 发布产出事件
            await self._publish_output(state.declaration, output, event)
        except Exception as exc:
            # 执行失败 → ERROR
            state.status = "error"
            state.error_count += 1
            state.last_execution_at = datetime.now(UTC)
            state.current_task = None
            state.last_error = str(exc)

    def get_agent_status(self, project_id: str, agent_type: str) -> dict[str, Any] | None:
        """获取Agent运行时状态"""
        state = self._agents.get(project_id, {}).get(agent_type)
        if state is None:
            return None
        return {
            "agent_id": state.declaration.agent_id,
            "status": state.status,
            "current_task": state.current_task,
            "completed_count": state.completed_count,
            "error_count": state.error_count,
            "last_execution_at": state.last_execution_at,
        }

    async def _assemble_prompt(self, declaration: AgentDeclaration, event: Event) -> PromptInput:
        """7步Prompt组装流程
        Step1: system_prompt from declaration
        Step2: history from EventStore (correlation_id事件链)
        Step3: context — MVP为空
        Step4: memory — 步骤14实现，当前为空
        Step5: task from payload
        Step6: 合并为PromptInput → ModelAdapter.complete()
        """
        # Step1: system_prompt
        system_prompt = f"Role: {declaration.role}\nGoal: {declaration.goal}\n\n{declaration.backstory}"
        # Step2: history from EventStore
        correlation_id = event.correlation_id
        raw_events = await self._store.get_events_by_correlation(correlation_id)
        history = [
            EventSummary(
                event_type=e.event_type,
                participant_id=e.participant_id,
                participant_type=e.participant_type,
                # Why: MVP简化——粗暴截取payload字符串前200字符作为摘要；
                # Phase 2应改为从payload中提取关键字段或使用领域schema解析
                content=str(e.payload)[:200],
                created_at=e.created_at or datetime.now(UTC),
            )
            for e in raw_events
        ]
        # Step3: context — MVP为空
        # Step4: memory from AgentMemory
        # Why: load_memory_chain是同步文件I/O——MVP文件小、项目少，阻塞影响可忽略；
        # Phase 2迁移到数据库后改为async，或用aiofiles包装
        memory = ""
        if self._memory:
            memory = self._memory.load_memory_chain(event.project_id, declaration.agent_type)
        # Step5: task
        task = self._payload_to_task(declaration.agent_type, event.payload)
        # Step5.5: metadata — 从事件payload提取*_id字段，供Agent产出引用真实实体ID
        metadata: dict[str, Any] = {"project_id": event.project_id}
        for key, value in event.payload.items():
            if key.endswith("_id") and isinstance(value, str):
                metadata[key] = value
        return PromptInput(
            system_prompt=system_prompt,
            context="",
            memory=memory,
            task=task,
            history=history,
            model_config_obj=declaration.model_config_obj,
            metadata=metadata,
        )

    def _payload_to_task(self, agent_type: str, payload: dict[str, Any]) -> str:
        """事件payload → 自然语言任务描述转换"""
        if agent_type == "summary":
            return f"请总结以下讨论线程的消息内容：{payload.get('content', '')}"
        if agent_type == "decompose":
            consensus = "\n".join(str(c) for c in payload.get("consensus_points", []))
            actions = "\n".join(str(a) for a in payload.get("action_items", []))
            return f"请根据以下共识点和行动项，分解为可执行的代码任务：\n共识点：\n{consensus}\n行动项：\n{actions}"
        if agent_type == "execute":
            if "approved_tasks" in payload:
                tasks = "\n".join(str(t) for t in payload["approved_tasks"])
                return f"请执行以下审批通过的代码任务：\n{tasks}"
            issues = "\n".join(str(i) for i in payload.get("issues", []))
            suggestions = "\n".join(str(s) for s in payload.get("suggestions", []))
            return f"请根据以下修改意见重新生成产出：\n问题：\n{issues}\n建议：\n{suggestions}"
        return str(payload)

    async def _publish_output(self, declaration: AgentDeclaration, output: ModelOutput, trigger_event: Event) -> None:
        """将Agent产出发布为新事件到EventBus

        尝试解析ModelOutput.content为JSON结构化payload；若非JSON则作为content字段。
        Why: 投影handler期望payload顶层含领域字段（summary_id/tasks等），
        但LLM可能返回JSON字符串而非纯文本，需在发布时解析合并。
        """
        try:
            parsed = json.loads(output.content)
            if isinstance(parsed, dict):
                payload = parsed
            else:
                payload = {"content": output.content}
        except (json.JSONDecodeError, TypeError):
            payload = {"content": output.content}

        new_event = Event(
            event_id=str(uuid.uuid4()),
            project_id=trigger_event.project_id,
            event_type=declaration.output_event_type,
            participant_id=declaration.agent_id,
            participant_type="agent",
            participant_display_name=declaration.display_name,
            payload=payload,
            correlation_id=trigger_event.correlation_id,
            causation_id=trigger_event.event_id,
            created_at=datetime.now(UTC),
        )
        # Why: 先持久化再发布——若store成功但bus失败，事件已写入但未路由；
        # 若先bus再store，bus handler可能读到尚未持久化的事件。Phase 2需引入补偿逻辑
        await self._store.append(new_event)
        await self._bus.publish(new_event)
