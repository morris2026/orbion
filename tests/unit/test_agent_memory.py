"""Agent层次化记忆管理测试"""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.biz.agents.declarations import SUMMARY_DECLARATION
from app.biz.agents.memory import AgentMemory
from app.biz.agents.runtime import AgentRuntime
from app.config import Settings
from app.hub.events.bus import InProcessEventBus
from app.hub.events.store import EventStoreProtocol
from app.hub.events.types import Event, EventType

JWT_SECRET_TEST = "test-secret-for-agent-memory-tests"


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


def _make_settings(tmp_path: Path) -> Settings:
    return Settings(jwt_secret=JWT_SECRET_TEST, root_dir=str(tmp_path))


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


# -- MVP-FL-2.1: 三层记忆加载 --


class TestMvpFl2AgentMemory:
    def test_mvp_fl_2_1_three_level_loading(self, tmp_path: Path) -> None:
        """MVP-FL-2.1：在tmp_path下创建三层memory.md，load_memory_chain返回按顺序拼接的内容"""
        settings = _make_settings(tmp_path)
        mem = AgentMemory(settings)
        mem.write_memory(settings.platform_memory_path, "平台记忆")
        mem.write_memory(settings.project_memory_path("p1"), "项目记忆")
        mem.write_memory(settings.agent_memory_path("p1", "summary"), "Agent记忆")

        result = mem.load_memory_chain("p1", "summary")
        assert "平台记忆" in result
        assert "项目记忆" in result
        assert "Agent记忆" in result
        assert result.index("平台记忆") < result.index("项目记忆")
        assert result.index("项目记忆") < result.index("Agent记忆")

    def test_mvp_fl_2_2_platform_only(self, tmp_path: Path) -> None:
        """MVP-FL-2.2：只创建平台级memory.md，返回值只有平台级内容"""
        settings = _make_settings(tmp_path)
        mem = AgentMemory(settings)
        mem.write_memory(settings.platform_memory_path, "平台内容")

        result = mem.load_memory_chain("p1", "summary")
        assert result == "平台内容"

    def test_mvp_fl_2_3_no_memory_files(self, tmp_path: Path) -> None:
        """MVP-FL-2.3：无任何记忆文件，返回空字符串"""
        settings = _make_settings(tmp_path)
        mem = AgentMemory(settings)

        result = mem.load_memory_chain("p1", "summary")
        assert result == ""

    def test_mvp_fl_2_4_write_memory_creates_dirs(self, tmp_path: Path) -> None:
        """MVP-FL-2.4：写入记忆文件时自动创建中间目录"""
        settings = _make_settings(tmp_path)
        mem = AgentMemory(settings)
        agent_path = settings.agent_memory_path("p1", "summary")

        mem.write_memory(agent_path, "新记忆")

        assert agent_path.exists()
        assert agent_path.read_text(encoding="utf-8") == "新记忆"

    def test_mvp_fl_2_5_path_traversal_blocked(self, tmp_path: Path) -> None:
        """MVP-FL-2.5：绝对路径越界时抛ValueError"""
        settings = _make_settings(tmp_path)
        mem = AgentMemory(settings)

        with pytest.raises(ValueError, match="路径越界"):
            mem.write_memory(Path("/etc/passwd"), "内容")
        with pytest.raises(ValueError, match="路径越界"):
            mem.read_memory(Path("/etc/passwd"))

    def test_mvp_fl_2_6_reset_agent_memory(self, tmp_path: Path) -> None:
        """MVP-FL-2.6：reset_agent_memory清空内容但文件仍存在"""
        settings = _make_settings(tmp_path)
        mem = AgentMemory(settings)
        agent_path = settings.agent_memory_path("p1", "summary")
        mem.write_memory(agent_path, "有内容")

        mem.reset_agent_memory("p1", "summary")

        assert agent_path.exists()
        assert agent_path.read_text(encoding="utf-8") == ""

    def test_mvp_fl_2_7_no_correlation_id(self, tmp_path: Path) -> None:
        """MVP-FL-2.7：load_memory_chain不再接受correlation_id参数"""
        settings = _make_settings(tmp_path)
        mem = AgentMemory(settings)

        with pytest.raises(TypeError):
            mem.load_memory_chain("p1", "summary", correlation_id="corr-1")  # type: ignore[call-arg]


# -- 旧TC适配：使用新接口 --


async def test_tc14_1_three_level_loading(tmp_path: Path) -> None:
    """MVP-14.1: 写入3层memory.md→load_memory_chain(project_id, agent_type)
    返回3层内容拼接，顺序为平台→项目→Agent
    """
    settings = _make_settings(tmp_path)
    mem = AgentMemory(settings)
    mem.write_memory(settings.platform_memory_path, "平台默认：使用中文输出")
    mem.write_memory(settings.project_memory_path("proj-1"), "项目级：代码注释用英文")
    mem.write_memory(settings.agent_memory_path("proj-1", "summary"), "Agent级：先列共识点再列分歧点")

    result = mem.load_memory_chain("proj-1", "summary")
    assert "平台默认" in result
    assert "项目级" in result
    assert "Agent级" in result
    assert result.index("平台默认") < result.index("项目级")
    assert result.index("项目级") < result.index("Agent级")


async def test_tc14_3_layer_override(tmp_path: Path) -> None:
    """MVP-14.3: 后加载覆盖前面的设置（类似CSS层叠）"""
    settings = _make_settings(tmp_path)
    mem = AgentMemory(settings)
    mem.write_memory(settings.platform_memory_path, "- 使用英文输出")
    mem.write_memory(settings.agent_memory_path("proj-1", "summary"), "- 使用中文输出")

    result = mem.load_memory_chain("proj-1", "summary")
    assert "使用英文" in result
    assert "使用中文" in result
    assert result.index("使用英文") < result.index("使用中文")


async def test_tc14_4_missing_levels(tmp_path: Path) -> None:
    """MVP-14.4: 只写平台层→返回平台层内容，不报错"""
    settings = _make_settings(tmp_path)
    mem = AgentMemory(settings)
    mem.write_memory(settings.platform_memory_path, "平台内容")

    result = mem.load_memory_chain("proj-nonexist", "summary")
    assert "平台内容" in result


async def test_tc14_5_write_memory(tmp_path: Path) -> None:
    """MVP-14.5: write_memory写入→read_memory验证"""
    settings = _make_settings(tmp_path)
    mem = AgentMemory(settings)
    agent_path = settings.agent_memory_path("proj-1", "summary")
    mem.write_memory(agent_path, "# 总结助手偏好\n- 先列共识点")

    content = mem.read_memory(agent_path)
    assert "总结助手偏好" in content
    assert "先列共识点" in content


async def test_tc14_6_reset_memory(tmp_path: Path) -> None:
    """MVP-14.6: reset_agent_memory→文件仍存在但内容为空"""
    settings = _make_settings(tmp_path)
    mem = AgentMemory(settings)
    agent_path = settings.agent_memory_path("proj-1", "summary")
    mem.write_memory(agent_path, "有内容的记忆")

    mem.reset_agent_memory("proj-1", "summary")
    content = mem.read_memory(agent_path)
    assert content == ""
    assert agent_path.exists()


async def test_tc14_7_memory_in_prompt(tmp_path: Path) -> None:
    """MVP-14.7: memory内容出现在PromptInput.memory中"""
    settings = _make_settings(tmp_path)
    mem = AgentMemory(settings)
    mem.write_memory(settings.platform_memory_path, "平台默认：中文输出")
    mem.write_memory(settings.agent_memory_path("proj-1", "summary"), "总结偏好：先列共识点")

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


async def test_tc14_path_traversal_blocked(tmp_path: Path) -> None:
    """路径遍历攻击被阻止——绝对路径越界时抛ValueError"""
    settings = _make_settings(tmp_path)
    mem = AgentMemory(settings)
    with pytest.raises(ValueError, match="路径越界"):
        mem.write_memory(Path("/etc/passwd"), "恶意内容")
    with pytest.raises(ValueError, match="路径越界"):
        mem.read_memory(Path("/etc/passwd"))
