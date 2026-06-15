"""Git集成与审批后自动commit测试"""

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.biz.git.service import GitService
from app.config import Settings
from app.hub.events.bus import InProcessEventBus
from app.hub.events.projections import EventProjectionsProtocol
from app.hub.events.types import Event, EventType

JWT_SECRET_TEST = "test-secret-for-git-integration-tests"


def _make_settings(tmp_path: Path) -> Settings:
    return Settings(jwt_secret=JWT_SECRET_TEST, root_dir=str(tmp_path))


class MockProjections(EventProjectionsProtocol):
    """内存投影，提供get_output_by_id查询"""

    _outputs: list[dict[str, Any]]

    def __init__(self, event_bus: InProcessEventBus) -> None:
        super().__init__(event_bus)
        self._outputs = []

    async def connect(self) -> None:
        pass

    async def close(self) -> None:
        pass

    async def get_thread_messages(self, thread_id: str) -> list[dict[str, Any]]:
        return []

    async def get_execution_plans(
        self, project_id: str, thread_id: str | None = None, status: str | None = None
    ) -> list[dict[str, Any]]:
        return []

    async def get_plan_by_id(self, plan_id: str) -> dict[str, Any] | None:
        return None

    async def get_task_outputs(self, project_id: str, plan_id: str | None = None) -> list[dict[str, Any]]:
        return []

    async def get_output_by_id(self, output_id: str) -> dict[str, Any] | None:
        for o in self._outputs:
            if o.get("id") == output_id:
                return o
        return None

    async def get_project_members(self, project_id: str) -> list[dict[str, Any]]:
        return []


def _make_output_dict(
    output_id: str = str(uuid4()),
    project_id: str = "proj-1",
    task_id: str = "t-1",
    plan_id: str = "plan-1",
    output_type: str = "code",
    content: str = "def foo(): pass",
    diff: str | None = None,
    file_paths: list[str] | None = None,
    status: str = "generated",
    version: int = 1,
) -> dict[str, Any]:
    """构造内存投影中的产出行"""
    return {
        "id": output_id,
        "project_id": project_id,
        "task_id": task_id,
        "plan_id": plan_id,
        "output_type": output_type,
        "content": content,
        "diff": diff,
        "file_paths": file_paths or ["src/foo.py"],
        "status": status,
        "version": version,
        "created_at": datetime.now(UTC),
    }


def _make_approved_event(
    output_id: str = "out-1",
    project_id: str = "proj-1",
    feedback: str | None = None,
) -> Event:
    """构造TaskOutputApproved事件"""
    return Event(
        event_id=str(uuid4()),
        project_id=project_id,
        event_type=EventType.TaskOutputApproved,
        participant_id="user-1",
        participant_type="human",
        participant_display_name="TestUser",
        payload={"output_id": output_id, "feedback": feedback},
        correlation_id="plan-1",
        causation_id=output_id,
        created_at=datetime.now(UTC),
    )


def _make_revision_requested_event(
    output_id: str = "out-1",
    project_id: str = "proj-1",
    task_id: str = "t-1",
) -> Event:
    """构造TaskOutputRevisionRequested事件"""
    return Event(
        event_id=str(uuid4()),
        project_id=project_id,
        event_type=EventType.TaskOutputRevisionRequested,
        participant_id="user-1",
        participant_type="human",
        participant_display_name="TestUser",
        payload={"output_id": output_id, "task_id": task_id, "issues": ["问题1"], "suggestions": []},
        correlation_id="plan-1",
        causation_id=output_id,
        created_at=datetime.now(UTC),
    )


# -- MVP-17.1: 产出审批通过→Git commit --


async def test_tc17_1_approve_triggers_commit(tmp_path: Path) -> None:
    """MVP-17.1: 产出审批通过→GitService执行commit→查询git log→有新commit"""
    bus = InProcessEventBus()
    projections = MockProjections(bus)
    output_id = "out-1"
    output = _make_output_dict(
        output_id=output_id,
        content="def foo(): pass",
        file_paths=["src/foo.py"],
    )
    projections._outputs = [output]

    settings = _make_settings(tmp_path)
    _git_service = GitService(settings, bus, projections)
    await _git_service.ensure_repo("proj-1", "orbion")

    event = _make_approved_event(output_id=output_id, project_id="proj-1")
    await bus.publish(event)
    await bus.wait_for_pending()

    import git

    repo_path = settings.project_repo_path("proj-1", "orbion")
    repo = git.Repo(str(repo_path))
    commits = list(repo.iter_commits())
    assert len(commits) == 2
    assert output_id in commits[0].message
    committed_content = (repo_path / "src" / "foo.py").read_text()
    assert committed_content == "def foo(): pass"


# -- MVP-17.2: 产出要求修改→不触发commit --


async def test_tc17_2_revision_no_commit(tmp_path: Path) -> None:
    """MVP-17.2: 产出request-revision→查询git log→无新commit产生"""
    bus = InProcessEventBus()
    projections = MockProjections(bus)
    output_id = "out-1"
    output = _make_output_dict(output_id=output_id)
    projections._outputs = [output]

    settings = _make_settings(tmp_path)
    _git_service = GitService(settings, bus, projections)
    await _git_service.ensure_repo("proj-1", "orbion")

    import git

    repo_path = settings.project_repo_path("proj-1", "orbion")
    repo = git.Repo(str(repo_path))
    initial_count = len(list(repo.iter_commits()))

    event = _make_revision_requested_event(output_id=output_id)
    await bus.publish(event)
    await bus.wait_for_pending()

    final_count = len(list(repo.iter_commits()))
    assert final_count == initial_count


# -- MVP-17.3: 产出审批拒绝→不触发commit --


async def test_tc17_3_rejection_no_commit(tmp_path: Path) -> None:
    """MVP-17.3: TaskOutputRevisionRequested事件不触发commit"""
    bus = InProcessEventBus()
    projections = MockProjections(bus)
    output_id = "out-2"
    output = _make_output_dict(output_id=output_id)
    projections._outputs = [output]

    settings = _make_settings(tmp_path)
    _git_service = GitService(settings, bus, projections)
    await _git_service.ensure_repo("proj-1", "orbion")

    import git

    repo_path = settings.project_repo_path("proj-1", "orbion")
    repo = git.Repo(str(repo_path))
    initial_count = len(list(repo.iter_commits()))

    event = _make_revision_requested_event(output_id=output_id, task_id="t-2")
    await bus.publish(event)
    await bus.wait_for_pending()

    final_count = len(list(repo.iter_commits()))
    assert final_count == initial_count


# -- MVP-17.4: 本地repo不存在→自动初始化 --


async def test_tc17_4_auto_init_repo(tmp_path: Path) -> None:
    """MVP-17.4: repo不存在→产出审批通过→repo自动初始化→commit成功"""
    bus = InProcessEventBus()
    projections = MockProjections(bus)
    output_id = "out-1"
    output = _make_output_dict(
        output_id=output_id,
        content="print('hello')",
        file_paths=["hello.py"],
        project_id="proj-1",
    )
    projections._outputs = [output]

    settings = _make_settings(tmp_path)
    repo_path = settings.project_repo_path("proj-1", "orbion")
    assert not os.path.exists(str(repo_path))

    _git_service = GitService(settings, bus, projections)

    event = _make_approved_event(output_id=output_id, project_id="proj-1")
    await bus.publish(event)
    await bus.wait_for_pending()

    import git

    repo = git.Repo(str(repo_path))
    commits = list(repo.iter_commits())
    assert len(commits) == 2
    assert output_id in commits[0].message
    committed_content = (repo_path / "hello.py").read_text()
    assert committed_content == "print('hello')"


# -- git log查询 --


async def test_get_recent_commits(tmp_path: Path) -> None:
    """GitService.get_recent_commits按项目返回最近N条commit摘要"""
    bus = InProcessEventBus()
    projections = MockProjections(bus)
    output_id = "out-log-1"
    output = _make_output_dict(output_id=output_id, file_paths=["log_test.py"], project_id="proj-1")
    projections._outputs = [output]

    settings = _make_settings(tmp_path)
    git_service = GitService(settings, bus, projections)
    await git_service.ensure_repo("proj-1", "orbion")

    event = _make_approved_event(output_id=output_id, project_id="proj-1")
    await bus.publish(event)
    await bus.wait_for_pending()

    commits = git_service.get_recent_commits("proj-1", "orbion", limit=5)
    assert len(commits) >= 2
    assert output_id in commits[0]["message"]
    assert commits[0]["hexsha"] != ""


async def test_get_recent_commits_empty_repo(tmp_path: Path) -> None:
    """空repo（只有初始commit）→get_recent_commits返回1条"""
    bus = InProcessEventBus()
    projections = MockProjections(bus)

    settings = _make_settings(tmp_path)
    git_service = GitService(settings, bus, projections)
    await git_service.ensure_repo("proj-1", "orbion")

    commits = git_service.get_recent_commits("proj-1", "orbion", limit=10)
    assert len(commits) == 1
    assert "init" in commits[0]["message"]


# -- MVP-FL-3.1~3.5: GitService 按项目隔离 --


class TestMvpFl3GitProjectIsolation:
    async def test_mvp_fl_3_1_project_isolation(self, tmp_path: Path) -> None:
        """MVP-FL-3.1：两个项目各有独立.git/目录，仓库互相隔离"""
        bus = InProcessEventBus()
        projections = MockProjections(bus)
        settings = _make_settings(tmp_path)
        git_service = GitService(settings, bus, projections)

        await git_service.ensure_repo("p1", "orbion")
        await git_service.ensure_repo("p2", "orbion")

        p1_repo_path = settings.project_repo_path("p1", "orbion")
        p2_repo_path = settings.project_repo_path("p2", "orbion")
        assert (p1_repo_path / ".git").is_dir()
        assert (p2_repo_path / ".git").is_dir()

        import git as gitmod

        p1_repo = gitmod.Repo(str(p1_repo_path))
        p2_repo = gitmod.Repo(str(p2_repo_path))
        assert p1_repo.working_dir != p2_repo.working_dir

    async def test_mvp_fl_3_2_idempotent_ensure_repo(self, tmp_path: Path) -> None:
        """MVP-FL-3.2：项目仓库已存在，再次ensure_repo不报错"""
        bus = InProcessEventBus()
        projections = MockProjections(bus)
        settings = _make_settings(tmp_path)
        git_service = GitService(settings, bus, projections)

        await git_service.ensure_repo("p1", "orbion")
        await git_service.ensure_repo("p1", "orbion")

        import git as gitmod

        p1_repo_path = settings.project_repo_path("p1", "orbion")
        repo = gitmod.Repo(str(p1_repo_path))
        commits = list(repo.iter_commits())
        assert len(commits) == 1

    async def test_mvp_fl_3_3_output_writes_to_correct_project(self, tmp_path: Path) -> None:
        """MVP-FL-3.3：产出写入正确项目仓库"""
        bus = InProcessEventBus()
        projections = MockProjections(bus)
        settings = _make_settings(tmp_path)
        git_service = GitService(settings, bus, projections)

        await git_service.ensure_repo("p1", "orbion")
        await git_service.ensure_repo("p2", "orbion")

        output_id = "out-p1"
        output = _make_output_dict(
            output_id=output_id,
            content="p1 code",
            file_paths=["src/main.py"],
            project_id="p1",
        )
        projections._outputs = [output]

        event = _make_approved_event(output_id=output_id, project_id="p1")
        await bus.publish(event)
        await bus.wait_for_pending()

        p1_repo_path = settings.project_repo_path("p1", "orbion")
        p2_repo_path = settings.project_repo_path("p2", "orbion")
        assert (p1_repo_path / "src" / "main.py").exists()
        assert not (p2_repo_path / "src" / "main.py").exists()

    async def test_mvp_fl_3_4_missing_project_id_skips(self, tmp_path: Path) -> None:
        """MVP-FL-3.4：事件project_id为空字符串时跳过，不抛异常"""
        bus = InProcessEventBus()
        projections = MockProjections(bus)
        settings = _make_settings(tmp_path)
        GitService(settings, bus, projections)

        output_id = "out-noproj"
        output = _make_output_dict(output_id=output_id, file_paths=["src/x.py"])
        projections._outputs = [output]

        event = Event(
            event_id=str(uuid4()),
            project_id="",
            event_type=EventType.TaskOutputApproved,
            participant_id="user-1",
            participant_type="human",
            participant_display_name="Test",
            payload={"output_id": output_id},
            correlation_id="corr-1",
            created_at=datetime.now(UTC),
        )
        await bus.publish(event)
        await bus.wait_for_pending()

        assert not settings.projects_dir.exists()

    async def test_mvp_fl_3_5_commits_per_project(self, tmp_path: Path) -> None:
        """MVP-FL-3.5：get_recent_commits按项目查询，各项目commit独立"""
        bus = InProcessEventBus()
        projections = MockProjections(bus)
        settings = _make_settings(tmp_path)
        git_service = GitService(settings, bus, projections)

        await git_service.ensure_repo("p1", "orbion")
        await git_service.ensure_repo("p2", "orbion")

        # p1: 1个审批commit
        output1 = _make_output_dict(output_id="out-p1-1", content="p1v1", file_paths=["a.py"], project_id="p1")
        projections._outputs = [output1]
        await bus.publish(_make_approved_event(output_id="out-p1-1", project_id="p1"))
        await bus.wait_for_pending()

        # p2: 2个审批commit
        output2a = _make_output_dict(output_id="out-p2-1", content="p2v1", file_paths=["b.py"], project_id="p2")
        output2b = _make_output_dict(output_id="out-p2-2", content="p2v2", file_paths=["c.py"], project_id="p2")
        projections._outputs = [output2a]
        await bus.publish(_make_approved_event(output_id="out-p2-1", project_id="p2"))
        await bus.wait_for_pending()
        projections._outputs = [output2b]
        await bus.publish(_make_approved_event(output_id="out-p2-2", project_id="p2"))
        await bus.wait_for_pending()

        p1_commits = git_service.get_recent_commits("p1", "orbion", limit=10)
        p2_commits = git_service.get_recent_commits("p2", "orbion", limit=10)

        # p1: 1初始 + 1审批 = 2
        assert len(p1_commits) == 2
        # p2: 1初始 + 2审批 = 3
        assert len(p2_commits) == 3

    async def test_mvp_fl_3_6_nonexistent_repo_returns_empty(self, tmp_path: Path) -> None:
        """MVP-FL-3.6：get_recent_commits查询不存在的仓库→返回空列表不抛异常"""
        bus = InProcessEventBus()
        projections = MockProjections(bus)
        settings = _make_settings(tmp_path)
        git_service = GitService(settings, bus, projections)

        commits = git_service.get_recent_commits("nonexistent-project", "orbion")
        assert commits == []
