"""Agent层次化记忆管理测试"""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.biz.agents.declarations import SUMMARY_DECLARATION
from app.biz.agents.memory import AgentMemory
from app.biz.agents.runtime import AgentRuntime
from app.hub.events.bus import InProcessEventBus
from app.hub.events.store import EventStoreProtocol
from app.hub.events.types import Event, EventType


class MockEventStore(EventStoreProtocol):
    appended: list[Event]

    def __init__(self) -> None:
        self.appended = []

    async def append(self, event: Event) -> None:
        self.appended.append(event)

    async def connect(self) -> None:
        pass

    async def close(self) -> None:
        pass

    async def get_events_by_correlation(self, correlation_id: str, limit: int = 100) -> list[Event]:
        return []

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


# -- MVP-14.1: 层次加载平台→项目→Agent --


async def test_tc14_1_three_level_loading(tmp_path: Path) -> None:
    """MVP-14.1: 写入3层memory.md→load_memory_chain(project_id, agent_type)
    返回3层内容拼接，顺序为平台→项目→Agent
    """
    mem = AgentMemory(str(tmp_path))
    # 写入3层
    mem.write_memory("platform", "平台默认：使用中文输出")
    mem.write_memory("project/proj-1", "项目级：代码注释用英文")
    mem.write_memory("project/proj-1/agents/summary", "Agent级：先列共识点再列分歧点")

    result = mem.load_memory_chain("proj-1", "summary")
    assert "平台默认" in result
    assert "项目级" in result
    assert "Agent级" in result
    # 顺序：平台在前，Agent在后
    assert result.index("平台默认") < result.index("项目级")
    assert result.index("项目级") < result.index("Agent级")


# -- MVP-14.2: 任务级memory加载 --


async def test_tc14_2_task_level_loading(tmp_path: Path) -> None:
    """MVP-14.2: 写入4层memory.md→load_memory_chain(project_id, agent_type, correlation_id)
    返回4层内容拼接，任务层在最末
    """
    mem = AgentMemory(str(tmp_path))
    mem.write_memory("platform", "平台")
    mem.write_memory("project/proj-1", "项目")
    mem.write_memory("project/proj-1/agents/summary", "Agent")
    mem.write_memory("project/proj-1/tasks/corr-task1", "任务级上下文")

    result = mem.load_memory_chain("proj-1", "summary", "corr-task1")
    assert "任务级上下文" in result
    assert result.index("Agent") < result.index("任务级上下文")


# -- MVP-14.3: 后加载覆盖前面的设置 --


async def test_tc14_3_layer_override(tmp_path: Path) -> None:
    """MVP-14.3: 平台层写"使用英文"→Agent层写"使用中文"→最终"使用中文"生效
    后加载覆盖前面的设置（类似CSS层叠）
    """
    mem = AgentMemory(str(tmp_path))
    mem.write_memory("platform", "- 使用英文输出")
    mem.write_memory("project/proj-1/agents/summary", "- 使用中文输出")

    result = mem.load_memory_chain("proj-1", "summary")
    # 两层都加载，Agent层在后覆盖平台层——排序断言验证CSS层叠语义
    assert "使用英文" in result
    assert "使用中文" in result
    assert result.index("使用英文") < result.index("使用中文")


# -- MVP-14.4: 不存在的层级→空字符串 --


async def test_tc14_4_missing_levels(tmp_path: Path) -> None:
    """MVP-14.4: 只写平台层→load_memory_chain（无项目层和Agent层文件）
    返回平台层内容+空内容，不报错
    """
    mem = AgentMemory(str(tmp_path))
    mem.write_memory("platform", "平台内容")

    result = mem.load_memory_chain("proj-nonexist", "summary")
    assert "平台内容" in result


# -- MVP-14.5: write_memory写入指定层级 --


async def test_tc14_5_write_memory(tmp_path: Path) -> None:
    """MVP-14.5: write_memory("project/proj-1/agents/summary", "内容")→read_memory验证
    文件创建成功，内容正确
    """
    mem = AgentMemory(str(tmp_path))
    mem.write_memory("project/proj-1/agents/summary", "# 总结助手偏好\n- 先列共识点")

    content = mem.read_memory("project/proj-1/agents/summary")
    assert "总结助手偏好" in content
    assert "先列共识点" in content


# -- MVP-14.6: reset_agent_memory清空内容 --


async def test_tc14_6_reset_memory(tmp_path: Path) -> None:
    """MVP-14.6: write_memory→reset_agent_memory→read_memory
    返回空字符串，文件仍存在（不删除）
    """
    mem = AgentMemory(str(tmp_path))
    mem.write_memory("project/proj-1/agents/summary", "有内容的记忆")

    mem.reset_agent_memory("proj-1", "summary")
    content = mem.read_memory("project/proj-1/agents/summary")
    assert content == ""
    # 文件仍存在
    assert (tmp_path / "project" / "proj-1" / "agents" / "summary" / "memory.md").exists()


# -- MVP-14.7: memory注入PromptInput --


async def test_tc14_7_memory_in_prompt(tmp_path: Path) -> None:
    """MVP-14.7: 写入memory→Agent执行prompt组装→检查PromptInput.memory字段
    memory内容出现在PromptInput.memory中
    """
    mem = AgentMemory(str(tmp_path))
    mem.write_memory("platform", "平台默认：中文输出")
    mem.write_memory("project/proj-1/agents/summary", "总结偏好：先列共识点")

    bus = InProcessEventBus()
    store = MockEventStore()
    adapter = AsyncMock()
    runtime = AgentRuntime(bus, store, adapter, memory=mem)
    runtime.register("proj-1", SUMMARY_DECLARATION)

    state = runtime._agents["proj-1"]["summary"]
    event = _make_event(EventType.DiscussionMessageCreated, project_id="proj-1", payload={"content": "test"})
    prompt = await runtime._assemble_prompt(state.declaration, event)

    assert "中文输出" in prompt.memory
    assert "总结偏好" in prompt.memory


# -- 路径遍历安全 --


async def test_tc14_path_traversal_blocked(tmp_path: Path) -> None:
    """路径遍历攻击被阻止——path含..时抛ValueError"""
    mem = AgentMemory(str(tmp_path))
    with pytest.raises(ValueError, match="路径越界"):
        mem.read_memory("../../etc")
    with pytest.raises(ValueError, match="路径越界"):
        mem.write_memory("../../etc", "恶意内容")
