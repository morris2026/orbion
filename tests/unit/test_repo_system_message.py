"""RepoService 系统消息测试 — clone/init 前后发送系统消息"""

import uuid
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.biz.credentials.service import CredentialService
from app.biz.repos.service import RepoService
from app.biz.threads.service import ThreadService
from app.config import Settings
from app.hub.events.bus import InProcessEventBus

JWT_SECRET_TEST = "test-secret-for-repo-service"


def _make_settings(tmp_path: Path) -> Settings:
    return Settings(jwt_secret=JWT_SECRET_TEST, root_dir=str(tmp_path))


def _make_thread_service() -> tuple[ThreadService, AsyncMock]:
    event_store = AsyncMock()
    event_bus = InProcessEventBus()
    thread_read = AsyncMock()
    project_read = AsyncMock()
    return ThreadService(event_store, event_bus, thread_read, project_read), event_store


def _make_repo_service(tmp_path: Path) -> tuple[RepoService, AsyncMock]:
    settings = _make_settings(tmp_path)
    credential_service = CredentialService(settings)
    thread_service, event_store = _make_thread_service()
    repo_service = RepoService(settings, credential_service, thread_service)
    return repo_service, event_store


class TestRepoSystemMessages:
    """clone/init 前后发送系统消息"""

    @pytest.mark.asyncio
    async def test_init_sends_system_messages(self, tmp_path: Path) -> None:
        """init 成功：先发正在初始化，再发已初始化"""
        repo_service, event_store = _make_repo_service(tmp_path)
        project_id = "p1"
        thread_id = str(uuid.uuid4())

        result = await repo_service.add_repo(project_id, name="test-repo", thread_id=thread_id)

        assert "name" in result
        # 应发送 2 条系统消息
        assert event_store.append.await_count == 2

        events = [call.args[0] for call in event_store.append.call_args_list]
        # 第一条：正在初始化
        assert "初始化" in events[0].payload["content"]
        assert events[0].participant_type == "system"
        # 第二条：已初始化
        assert "已初始化" in events[1].payload["content"]
        assert events[1].participant_type == "system"

    @pytest.mark.asyncio
    async def test_clone_failure_sends_system_messages(self, tmp_path: Path) -> None:
        """clone 失败：先发正在克隆，再发克隆失败"""
        repo_service, event_store = _make_repo_service(tmp_path)
        project_id = "p1"
        thread_id = str(uuid.uuid4())

        result = await repo_service.add_repo(
            project_id, url="https://nonexistent.invalid/repo.git", thread_id=thread_id
        )

        assert "error" in result
        # 应发送 2 条系统消息
        assert event_store.append.await_count == 2

        events = [call.args[0] for call in event_store.append.call_args_list]
        # 第一条：正在克隆
        assert "克隆" in events[0].payload["content"]
        assert events[0].participant_type == "system"
        # 第二条：克隆失败
        assert "失败" in events[1].payload["content"]
        assert events[1].participant_type == "system"

    @pytest.mark.asyncio
    async def test_no_system_messages_without_thread_id(self, tmp_path: Path) -> None:
        """无 thread_id 时不发送系统消息（向后兼容）"""
        repo_service, event_store = _make_repo_service(tmp_path)

        result = await repo_service.add_repo("p1", name="test-repo")

        assert "name" in result
        assert event_store.append.await_count == 0
