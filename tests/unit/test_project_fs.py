"""项目创建/删除联动文件系统测试"""

from pathlib import Path

from app.biz.projects.service import ProjectService
from app.config import Settings
from app.hub.events.store import EventStoreProtocol
from app.hub.events.types import Event

JWT_SECRET_TEST = "test-secret-for-project-fs-tests"


def _make_settings(tmp_path: Path) -> Settings:
    return Settings(jwt_secret=JWT_SECRET_TEST, root_dir=str(tmp_path))


class MockEventStore(EventStoreProtocol):
    def __init__(self) -> None:
        self.appended: list[Event] = []

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


class TestMvpFl5ProjectFs:
    def test_mvp_fl_5_1_create_project_init_dirs(self, tmp_path: Path) -> None:
        """MVP-FL-5.1：项目创建后初始化文件系统目录"""
        settings = _make_settings(tmp_path)
        project_id = "proj-fs-1"

        ProjectService._init_project_dirs(settings, project_id)

        project_dir = settings.project_dir(project_id)
        assert project_dir.is_dir()
        assert settings.project_memory_path(project_id).exists()
        assert (project_dir / "repo").is_dir()

    def test_mvp_fl_5_2_delete_project_cleanup_dirs(self, tmp_path: Path) -> None:
        """MVP-FL-5.2：项目删除后清理文件系统目录（含 git 仓库）"""
        settings = _make_settings(tmp_path)
        project_id = "proj-fs-2"

        ProjectService._init_project_dirs(settings, project_id)
        repo_path = settings.project_repo_path(project_id, "orbion")
        repo_path.mkdir(parents=True, exist_ok=True)
        (repo_path / "main.py").write_text("code", encoding="utf-8")

        ProjectService._cleanup_project_dirs(settings, project_id)

        assert not settings.project_dir(project_id).exists()

    def test_mvp_fl_5_3_delete_project_with_agent_memory(self, tmp_path: Path) -> None:
        """MVP-FL-5.3：删除项目时 Agent 记忆文件随项目目录一起删除"""
        settings = _make_settings(tmp_path)
        project_id = "proj-fs-3"

        ProjectService._init_project_dirs(settings, project_id)
        agent_mem = settings.agent_memory_path(project_id, "summary")
        agent_mem.parent.mkdir(parents=True, exist_ok=True)
        agent_mem.write_text("Agent记忆", encoding="utf-8")

        ProjectService._cleanup_project_dirs(settings, project_id)

        assert not agent_mem.exists()
        assert not settings.project_dir(project_id).exists()

    def test_mvp_fl_5_4_delete_nonexistent_dirs_no_error(self, tmp_path: Path) -> None:
        """MVP-FL-5.4：目录不存在时不抛异常"""
        settings = _make_settings(tmp_path)
        project_id = "proj-nonexistent"

        ProjectService._cleanup_project_dirs(settings, project_id)
