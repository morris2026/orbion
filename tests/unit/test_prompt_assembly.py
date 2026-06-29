"""模型适配与Prompt组装流程测试"""

import json
from datetime import UTC, datetime
from typing import Any, Literal
from unittest.mock import AsyncMock

from app.biz.agents.adapters._legacy.base import EventSummary, ModelConfig, ModelOutput, PromptInput
from app.biz.agents.adapters._legacy.claude import ClaudeAdapter
from app.biz.agents.declarations import SUMMARY_DECLARATION
from app.biz.agents.runtime import AgentRuntime
from app.hub.events.bus import InProcessEventBus
from app.hub.events.store import EventStoreProtocol
from app.hub.events.types import Event, EventType


class MockEventStore(EventStoreProtocol):
    """可控mock EventStore——记录append + 返回预设history"""

    appended: list[Event]

    def __init__(self, history_events: list[Event] | None = None) -> None:
        self.appended = []
        self._history = history_events or []

    async def append(self, event: Event) -> None:
        self.appended.append(event)

    async def connect(self) -> None:
        pass

    async def close(self) -> None:
        pass

    async def get_events_by_correlation(self, correlation_id: str, limit: int = 100) -> list[Event]:
        return self._history

    async def get_events_by_project(
        self, project_id: str, event_type: str | None = None, limit: int = 50
    ) -> list[Event]:
        return []


def _make_event(
    event_type: str | EventType,
    project_id: str = "proj-1",
    correlation_id: str = "corr-1",
    payload: dict[str, Any] = {},
) -> Event:
    return Event(
        event_id="evt-trigger",
        project_id=project_id,
        event_type=str(event_type),
        participant_id="user-1",
        participant_type="human",
        participant_display_name="Test",
        payload=payload,
        correlation_id=correlation_id,
        created_at=datetime.now(UTC),
    )


def _make_history_event(
    event_id: str,
    participant_type: Literal["human", "agent"] = "human",
    content: str = "hello",
) -> Event:
    """生成用于history的事件"""
    return Event(
        event_id=event_id,
        project_id="proj-1",
        event_type="DiscussionMessageCreated",
        participant_id="user-1" if participant_type == "human" else "agent-summary-abc",
        participant_type=participant_type,
        participant_display_name="User" if participant_type == "human" else "总结助手",
        payload={"thread_id": "t1", "content": content},
        correlation_id="corr-1",
        created_at=datetime(2026, 6, 3, 3, 0, 0, tzinfo=UTC),
    )


# -- MVP-13.1: system_prompt组装 --


async def test_tc13_1_system_prompt() -> None:
    """MVP-13.1: 从AgentDeclaration取role/goal/backstory→组装system_prompt
    system_prompt含role/goal/backstory三段内容
    """
    bus = InProcessEventBus()
    store = MockEventStore()
    adapter = AsyncMock()
    runtime = AgentRuntime(bus, store, adapter)
    runtime.register("proj-1", SUMMARY_DECLARATION)

    state = runtime._agents["proj-1"]["summary"]
    event = _make_event(EventType.DiscussionMessageCreated, payload={"content": "test"})
    prompt = await runtime._assemble_prompt(state.declaration, event)

    assert "讨论总结专家" in prompt.system_prompt
    assert "从讨论线程中提炼共识点、分歧点和行动项" in prompt.system_prompt
    assert "你是一个讨论总结 Agent" in prompt.system_prompt


# -- MVP-13.2: history从correlation_id事件链获取 --


async def test_tc13_2_history_from_correlation() -> None:
    """MVP-13.2: mock EventStore返回事件列表→转换为EventSummary
    human→role="user"，agent→role="assistant"；字段正确
    """
    bus = InProcessEventBus()
    history_events = [
        _make_history_event("evt-h1", "human", "第一条消息"),
        _make_history_event("evt-a1", "agent", "第一条总结"),
    ]
    store = MockEventStore(history_events=history_events)
    adapter = AsyncMock()
    runtime = AgentRuntime(bus, store, adapter)
    runtime.register("proj-1", SUMMARY_DECLARATION)

    state = runtime._agents["proj-1"]["summary"]
    event = _make_event(EventType.DiscussionMessageCreated, correlation_id="corr-1")
    prompt = await runtime._assemble_prompt(state.declaration, event)

    assert len(prompt.history) == 2
    h1 = prompt.history[0]
    assert h1.event_type == "DiscussionMessageCreated"
    assert h1.participant_id == "user-1"
    assert h1.participant_type == "human"
    assert h1.content == str({"thread_id": "t1", "content": "第一条消息"})
    h2 = prompt.history[1]
    assert h2.participant_type == "agent"
    assert "第一条总结" in h2.content


# -- MVP-13.3: task描述转换规则 --


async def test_tc13_3_task_conversion() -> None:
    """MVP-13.3: 4种事件payload→转换为task描述"""
    bus = InProcessEventBus()
    store = MockEventStore()
    adapter = AsyncMock()
    runtime = AgentRuntime(bus, store, adapter)

    # summary: DiscussionMessageCreated
    task_summary = runtime._payload_to_task("summary", {"content": "讨论内容"})
    assert "讨论线程" in task_summary
    assert "讨论内容" in task_summary

    # decompose: DiscussionSummaryGenerated
    task_decompose = runtime._payload_to_task("decompose", {"consensus_points": ["c1"], "action_items": ["a1"]})
    assert "共识点" in task_decompose
    assert "行动项" in task_decompose

    # execute: ExecutionPlanApproved
    task_execute = runtime._payload_to_task("execute", {"approved_tasks": ["task1"]})
    assert "审批通过的代码任务" in task_execute

    # execute: TaskOutputRevisionRequested
    task_revision = runtime._payload_to_task("execute", {"issues": ["i1"], "suggestions": ["s1"]})
    assert "修改意见" in task_revision


# -- MVP-13.4: PromptInput合并 --


async def test_tc13_4_prompt_input_merge() -> None:
    """MVP-13.4: 组装7步各部分→合并为PromptInput
    system_prompt/context(memory=空)/task/history字段齐全
    """
    bus = InProcessEventBus()
    history_events = [_make_history_event("evt-h1", "human", "消息")]
    store = MockEventStore(history_events=history_events)
    adapter = AsyncMock()
    runtime = AgentRuntime(bus, store, adapter)
    runtime.register("proj-1", SUMMARY_DECLARATION)

    state = runtime._agents["proj-1"]["summary"]
    event = _make_event(EventType.DiscussionMessageCreated, correlation_id="corr-1")
    prompt = await runtime._assemble_prompt(state.declaration, event)

    # system_prompt非空
    assert prompt.system_prompt != ""
    # context为空（MVP）
    assert prompt.context == ""
    # memory为空（记忆模块未实现）
    assert prompt.memory == ""
    # task非空
    assert prompt.task != ""
    # history非空（从EventStore获取）
    assert len(prompt.history) >= 1


# -- MVP-13.5: mock ModelAdapter→产出解析→新事件构建 --


async def test_tc13_5_output_to_new_event() -> None:
    """MVP-13.5: dispatch→mock ModelAdapter→产出→新事件构建
    event_type与AgentDeclaration.output_event_type一致；
    correlation_id继承触发事件；causation_id指向触发事件event_id；
    payload内容与ModelOutput对应
    """
    bus = InProcessEventBus()
    store = MockEventStore()
    mock_adapter = AsyncMock()
    mock_adapter.complete = AsyncMock(return_value=ModelOutput(content="总结内容"))
    runtime = AgentRuntime(bus, store, mock_adapter)
    runtime.register("proj-1", SUMMARY_DECLARATION)

    event = _make_event(EventType.DiscussionMessageCreated, correlation_id="corr-test")
    await runtime.dispatch("proj-1", "summary", event)

    # 检查store.append写入了新事件
    assert len(store.appended) == 1
    new_event = store.appended[0]
    # event_type与declaration一致
    assert new_event.event_type == SUMMARY_DECLARATION.output_event_type
    # correlation_id继承触发事件
    assert new_event.correlation_id == "corr-test"
    # causation_id指向触发事件event_id
    assert new_event.causation_id == "evt-trigger"
    # payload内容与ModelOutput对应
    assert new_event.payload["content"] == "总结内容"
    # participant信息正确
    assert new_event.participant_type == "agent"


# -- _publish_output JSON解析路径 --


async def test_publish_output_json_parsed_as_payload() -> None:
    """_publish_output：ModelOutput返回有效JSON字符串→payload被解析为结构化字典
    投影handler期望payload顶层含领域字段而非{"content": "<json-string>"}
    """
    bus = InProcessEventBus()
    store = MockEventStore()
    mock_adapter = AsyncMock()
    summary_json = json.dumps(
        {
            "summary_id": "s-1",
            "thread_id": "t-1",
            "consensus_points": ["共识点1"],
            "divergence_points": [],
            "action_items": [],
            "knowledge_references": [],
        }
    )
    mock_adapter.complete = AsyncMock(return_value=ModelOutput(content=summary_json))
    runtime = AgentRuntime(bus, store, mock_adapter)
    runtime.register("proj-1", SUMMARY_DECLARATION)

    event = _make_event(EventType.DiscussionMessageCreated, correlation_id="corr-json")
    await runtime.dispatch("proj-1", "summary", event)

    assert len(store.appended) == 1
    new_event = store.appended[0]
    # payload是解析后的JSON字典，不是{"content": "<json-string>"}
    assert "summary_id" in new_event.payload
    assert new_event.payload["summary_id"] == "s-1"
    assert new_event.payload["thread_id"] == "t-1"
    assert "content" not in new_event.payload


async def test_publish_output_non_json_fallback_to_content() -> None:
    """_publish_output：ModelOutput返回非JSON字符串→payload回退为{"content": ...}"""
    bus = InProcessEventBus()
    store = MockEventStore()
    mock_adapter = AsyncMock()
    mock_adapter.complete = AsyncMock(return_value=ModelOutput(content="纯文本产出"))
    runtime = AgentRuntime(bus, store, mock_adapter)
    runtime.register("proj-1", SUMMARY_DECLARATION)

    event = _make_event(EventType.DiscussionMessageCreated, correlation_id="corr-text")
    await runtime.dispatch("proj-1", "summary", event)

    assert len(store.appended) == 1
    new_event = store.appended[0]
    assert new_event.payload["content"] == "纯文本产出"


async def test_publish_output_json_array_fallback_to_content() -> None:
    """_publish_output：ModelOutput返回JSON数组（非dict）→payload回退为{"content": ...}"""
    bus = InProcessEventBus()
    store = MockEventStore()
    mock_adapter = AsyncMock()
    mock_adapter.complete = AsyncMock(return_value=ModelOutput(content='["a", "b"]'))
    runtime = AgentRuntime(bus, store, mock_adapter)
    runtime.register("proj-1", SUMMARY_DECLARATION)

    event = _make_event(EventType.DiscussionMessageCreated, correlation_id="corr-arr")
    await runtime.dispatch("proj-1", "summary", event)

    assert len(store.appended) == 1
    new_event = store.appended[0]
    assert new_event.payload["content"] == '["a", "b"]'


# -- MVP-13.6: ClaudeAdapter调用格式 --


async def test_tc13_6_claude_adapter_format() -> None:
    """MVP-13.6: 构建PromptInput→ClaudeAdapter._build_system/_build_messages
    system含role/goal/backstory+memory+context；
    messages含history(user/assistant映射)+task(user role)
    """
    adapter = ClaudeAdapter(api_key="sk-test-key")

    prompt = PromptInput(
        system_prompt="Role: 讨论总结专家\nGoal: 提炼共识",
        context="知识上下文内容",
        memory="行为偏好内容",
        task="请总结以下讨论",
        model_config_obj=ModelConfig(model_id="claude-haiku-4-5-20251001", temperature=0.3, max_tokens=2048),
        history=[
            EventSummary(
                event_type="DiscussionMessageCreated",
                participant_id="user-1",
                participant_type="human",
                content="第一条消息",
                created_at=datetime(2026, 6, 3, 3, 0, 0, tzinfo=UTC),
            ),
            EventSummary(
                event_type="DiscussionSummaryGenerated",
                participant_id="agent-summary-abc",
                participant_type="agent",
                content="总结内容",
                created_at=datetime(2026, 6, 3, 3, 10, 0, tzinfo=UTC),
            ),
        ],
    )

    system = adapter._build_system(prompt)
    assert "讨论总结专家" in system
    assert "提炼共识" in system
    assert "行为偏好内容" in system
    assert "知识上下文内容" in system

    messages = adapter._build_messages(prompt)
    # history映射：human→user, agent→assistant
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "第一条消息"
    assert messages[1]["role"] == "assistant"
    assert messages[1]["content"] == "总结内容"
    # task在最后，以user角色
    assert messages[-1]["role"] == "user"
    assert messages[-1]["content"] == "请总结以下讨论"


# -- MVP-13.6补充: memory/context为空时不添加段落 --


async def test_tc13_6_empty_memory_context() -> None:
    """MVP-13.6补充: memory/context为空时，_build_system不添加段落标题"""
    adapter = ClaudeAdapter(api_key="sk-test-key")

    prompt = PromptInput(
        system_prompt="Role: 专家",
        context="",
        memory="",
        task="任务描述",
        model_config_obj=ModelConfig(model_id="claude-haiku-4-5-20251001"),
        history=[],
    )

    system = adapter._build_system(prompt)
    assert "行为偏好" not in system
    assert "知识上下文" not in system

    messages = adapter._build_messages(prompt)
    # 无history，只有task
    assert len(messages) == 1
    assert messages[0]["role"] == "user"


# -- metadata：事件payload *_id字段提取到PromptInput.metadata --


async def test_metadata_from_event_payload_ids() -> None:
    """metadata提取：事件payload中以_id结尾的字符串字段→自动进入PromptInput.metadata
    project_id始终包含；非_id字段不进入metadata
    """
    bus = InProcessEventBus()
    store = MockEventStore()
    adapter = AsyncMock()
    runtime = AgentRuntime(bus, store, adapter)
    runtime.register("proj-1", SUMMARY_DECLARATION)

    state = runtime._agents["proj-1"]["summary"]
    event = _make_event(
        EventType.DiscussionMessageCreated,
        project_id="proj-1",
        payload={"thread_id": "thread-abc", "content": "讨论内容", "request_summary": True},
    )
    prompt = await runtime._assemble_prompt(state.declaration, event)

    # thread_id从payload提取到metadata
    assert prompt.metadata["thread_id"] == "thread-abc"
    # project_id始终包含
    assert prompt.metadata["project_id"] == "proj-1"
    # 非_id字段（content、request_summary）不进入metadata
    assert "content" not in prompt.metadata
    assert "request_summary" not in prompt.metadata


async def test_metadata_multiple_ids() -> None:
    """metadata提取：多个*_id字段同时提取（如plan_id+thread_id）"""
    bus = InProcessEventBus()
    store = MockEventStore()
    adapter = AsyncMock()
    runtime = AgentRuntime(bus, store, adapter)
    runtime.register("proj-1", SUMMARY_DECLARATION)

    state = runtime._agents["proj-1"]["summary"]
    event = _make_event(
        EventType.ExecutionPlanProposed,
        project_id="proj-2",
        payload={"plan_id": "plan-xyz", "thread_id": "thread-abc", "tasks": []},
    )
    prompt = await runtime._assemble_prompt(state.declaration, event)

    assert prompt.metadata["plan_id"] == "plan-xyz"
    assert prompt.metadata["thread_id"] == "thread-abc"
    assert prompt.metadata["project_id"] == "proj-2"


async def test_metadata_only_project_id_when_no_payload_ids() -> None:
    """metadata提取：payload无*_id字段→metadata只含project_id"""
    bus = InProcessEventBus()
    store = MockEventStore()
    adapter = AsyncMock()
    runtime = AgentRuntime(bus, store, adapter)
    runtime.register("proj-1", SUMMARY_DECLARATION)

    state = runtime._agents["proj-1"]["summary"]
    event = _make_event(
        EventType.ProjectCreated,
        project_id="proj-new",
        payload={"name": "新项目", "description": "描述"},
    )
    prompt = await runtime._assemble_prompt(state.declaration, event)

    # 无*_id字段，只有project_id
    assert prompt.metadata == {"project_id": "proj-new"}
