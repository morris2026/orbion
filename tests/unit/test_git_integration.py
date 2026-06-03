"""步骤17 UT：TC-17.1–17.4 — Git集成与审批后自动commit"""

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.biz.git.service import GitService
from app.hub.events.bus import InProcessEventBus
from app.hub.events.projections import EventProjectionsProtocol
from app.hub.events.types import Event, EventType


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


# -- TC-17.1: 产出审批通过→Git commit --


async def test_tc17_1_approve_triggers_commit(tmp_path: Path) -> None:
    """TC-17.1: 产出审批通过→GitService执行commit→查询git log→有新commit
    commit消息含产出信息；commit内容与file_paths和content一致
    """
    bus = InProcessEventBus()
    projections = MockProjections(bus)
    output_id = "out-1"
    output = _make_output_dict(
        output_id=output_id,
        content="def foo(): pass",
        file_paths=["src/foo.py"],
    )
    projections._outputs = [output]

    repo_path = str(tmp_path / "repo")
    _git_service = GitService(repo_path, bus, projections)
    await _git_service.ensure_repo()

    # 发布审批通过事件
    event = _make_approved_event(output_id=output_id)
    await bus.publish(event)
    await bus.wait_for_pending()

    # 验证：git log有新commit
    import git

    repo = git.Repo(repo_path)
    commits = list(repo.iter_commits())
    # 1初始commit + 1审批commit = 2
    assert len(commits) == 2
    # commit消息含产出信息
    assert output_id in commits[0].message
    # commit内容：file_paths中的文件存在且内容与content一致
    committed_content = (Path(repo_path) / "src" / "foo.py").read_text()
    assert committed_content == "def foo(): pass"


# -- TC-17.2: 产出要求修改→不触发commit --


async def test_tc17_2_revision_no_commit(tmp_path: Path) -> None:
    """TC-17.2: 产出request-revision→查询git log→无新commit产生"""
    bus = InProcessEventBus()
    projections = MockProjections(bus)
    output_id = "out-1"
    output = _make_output_dict(output_id=output_id)
    projections._outputs = [output]

    repo_path = str(tmp_path / "repo")
    _git_service = GitService(repo_path, bus, projections)
    await _git_service.ensure_repo()

    import git

    repo = git.Repo(repo_path)
    initial_count = len(list(repo.iter_commits()))

    # 发布request-revision事件
    event = _make_revision_requested_event(output_id=output_id)
    await bus.publish(event)
    await bus.wait_for_pending()

    # 验证：无新commit产生
    final_count = len(list(repo.iter_commits()))
    assert final_count == initial_count


# -- TC-17.3: 产出审批拒绝→不触发commit --


async def test_tc17_3_rejection_no_commit(tmp_path: Path) -> None:
    """TC-17.3: TaskOutputRevisionRequested事件不触发commit
    （当前产出无reject端点，TC-17.3的意图与TC-17.2等价但独立验证）
    """
    bus = InProcessEventBus()
    projections = MockProjections(bus)
    output_id = "out-2"
    output = _make_output_dict(output_id=output_id)
    projections._outputs = [output]

    repo_path = str(tmp_path / "repo")
    _git_service = GitService(repo_path, bus, projections)
    await _git_service.ensure_repo()

    import git

    repo = git.Repo(repo_path)
    initial_count = len(list(repo.iter_commits()))

    # 与TC-17.2相同事件类型，但独立output_id验证
    event = _make_revision_requested_event(output_id=output_id, task_id="t-2")
    await bus.publish(event)
    await bus.wait_for_pending()

    final_count = len(list(repo.iter_commits()))
    assert final_count == initial_count


# -- TC-17.4: 本地repo不存在→自动初始化 --


async def test_tc17_4_auto_init_repo(tmp_path: Path) -> None:
    """TC-17.4: 删除本地repo→产出审批通过→repo自动初始化（git init）→commit成功执行"""
    bus = InProcessEventBus()
    projections = MockProjections(bus)
    output_id = "out-1"
    output = _make_output_dict(
        output_id=output_id,
        content="print('hello')",
        file_paths=["hello.py"],
    )
    projections._outputs = [output]

    # repo_path指向一个不存在的新目录
    repo_path = str(tmp_path / "new_repo")
    assert not os.path.exists(repo_path)

    _git_service = GitService(repo_path, bus, projections)

    # 发布审批通过事件（repo还不存在）
    event = _make_approved_event(output_id=output_id)
    await bus.publish(event)
    await bus.wait_for_pending()

    # 验证：repo自动初始化
    import git

    repo = git.Repo(repo_path)
    commits = list(repo.iter_commits())
    # 1初始commit + 1审批commit = 2
    assert len(commits) == 2
    assert output_id in commits[0].message
    # 内容一致
    committed_content = (Path(repo_path) / "hello.py").read_text()
    assert committed_content == "print('hello')"
