"""AgentService——Agent注册CQRS写端"""

import uuid
from datetime import UTC, datetime
from typing import Any

from app.biz.agents.declarations import BUILTIN_AGENT_DECLARATIONS
from app.biz.agents.runtime import AgentRuntime
from app.hub.auth.models import User
from app.hub.events.bus import EventBus
from app.hub.events.store import EventStoreProtocol
from app.hub.events.types import AgentRegisteredPayload, Event, EventType
from app.hub.permissions.roles import AGENT_ROLE_BITS


class AgentService:
    """Agent注册——CQRS写端"""

    def __init__(self, event_store: EventStoreProtocol, event_bus: EventBus, runtime: AgentRuntime) -> None:
        self._event_store = event_store
        self._event_bus = event_bus
        self._runtime = runtime

    async def register_agent(
        self, project_id: str, agent_type: str, model_id: str, display_name: str, actor: User
    ) -> dict[str, Any]:
        """注册Agent到项目：1. 发布AgentRegistered事件→投影写入project_members
        2. AgentRuntime.register()→调度器可dispatch
        """
        # MVP每种agent_type只能注册一次
        if self._runtime.has_agent(project_id, agent_type):
            raise ValueError(f"项目 {project_id} 已注册 {agent_type} Agent，不允许重复注册")
        # 从模板创建声明
        template = BUILTIN_AGENT_DECLARATIONS[agent_type]
        # 生成唯一agent_id（模板ID替换为项目级唯一ID）
        agent_id = f"agent-{agent_type}-{uuid.uuid4().hex[:8]}"

        # 自动分配Agent权限位
        roles_bits = AGENT_ROLE_BITS[agent_type]
        role_names = [agent_type]

        # 发布AgentRegistered事件
        payload = AgentRegisteredPayload(
            agent_type=agent_type,
            model_id=model_id,
            subscribed_events=template.subscribed_events,
            roles=role_names,
        )
        event = Event(
            event_id=str(uuid.uuid4()),
            project_id=project_id,
            event_type=EventType.AgentRegistered,
            participant_id=agent_id,
            participant_type="agent",
            participant_display_name=display_name,
            payload=payload.model_dump(mode="json"),
            # Why: correlation_id应串联讨论链而非项目；Agent注册是独立操作，用自身event_id做correlation
            correlation_id=str(uuid.uuid4()),
            created_at=datetime.now(UTC),
        )
        await self._event_store.append(event)
        await self._event_bus.publish(event)

        # 注册到AgentRuntime
        declaration = template.model_copy(update={"agent_id": agent_id, "display_name": display_name})
        self._runtime.register(project_id, declaration)

        return {
            "participant_id": agent_id,
            "project_id": project_id,
            "type": "agent",
            "display_name": display_name,
            "agent_type": agent_type,
            "model_id": model_id,
            "status": "idle",
            "subscribed_events": template.subscribed_events,
            "roles": roles_bits,
        }
