"""TC-2.2~TC-2.4：Event模型、EventType枚举、EventPayload schema测试"""

import pytest
from pydantic import ValidationError


class TestEventModel:
    """TC-2.2：Event模型校验"""

    def test_tc2_2_event_valid_creation(self) -> None:
        """TC-2.2：正常创建Event实例"""
        from app.hub.events.types import Event

        event = Event(
            event_id="evt-001",
            project_id="proj-001",
            event_type="DiscussionMessageCreated",
            participant_id="user-001",
            participant_type="human",
            payload={"thread_id": "t-1", "content": "hello"},
            correlation_id="corr-001",
        )
        assert event.event_id == "evt-001"
        assert event.project_id == "proj-001"
        assert event.participant_type == "human"

    def test_tc2_2_event_project_id_required(self) -> None:
        """TC-2.2：project_id缺失报错"""
        from app.hub.events.types import Event

        with pytest.raises(ValidationError):
            Event(
                event_id="evt-001",
                event_type="DiscussionMessageCreated",
                participant_id="user-001",
                participant_type="human",
                payload={"thread_id": "t-1", "content": "hello"},
                correlation_id="corr-001",
            )  # type: ignore[call-arg]

    def test_tc2_2_event_participant_type_invalid(self) -> None:
        """TC-2.2：participant_type不在human/agent范围报错"""
        from app.hub.events.types import Event

        with pytest.raises(ValidationError):
            Event(
                event_id="evt-001",
                project_id="proj-001",
                event_type="DiscussionMessageCreated",
                participant_id="user-001",
                participant_type="robot",  # type: ignore[arg-type]
                payload={"thread_id": "t-1", "content": "hello"},
                correlation_id="corr-001",
            )

    def test_tc2_2_event_payload_default_empty_dict(self) -> None:
        """TC-2.2：payload默认为空dict"""
        from app.hub.events.types import Event

        event = Event(
            event_id="evt-001",
            project_id="proj-001",
            event_type="DiscussionMessageCreated",
            participant_id="user-001",
            participant_type="human",
            correlation_id="corr-001",
        )
        assert event.payload == {}


class TestEventTypeEnum:
    """TC-2.3：EventType枚举完整性"""

    def test_tc2_3_all_8_event_types_exist(self) -> None:
        """TC-2.3：8个MVP事件类型全部存在"""
        from app.hub.events.types import EventType

        expected_types = [
            "DiscussionMessageCreated",
            "DiscussionSummaryGenerated",
            "ExecutionPlanProposed",
            "ExecutionPlanApproved",
            "ExecutionPlanRejected",
            "TaskOutputGenerated",
            "TaskOutputApproved",
            "TaskOutputRevisionRequested",
        ]
        actual_names = [e.value for e in EventType]
        assert set(expected_types) == set(actual_names), f"缺少事件类型: {set(expected_types) - set(actual_names)}"

    def test_tc2_3_event_type_values_match_names(self) -> None:
        """TC-2.3：EventType枚举值与字符串名称一致"""
        from app.hub.events.types import EventType

        for et in EventType:
            assert et.value == et.name, f"EventType {et.name} 的值 {et.value} 不等于名称"


class TestDiscussionMessageCreatedPayload:
    """TC-2.4.1：DiscussionMessageCreated payload"""

    def test_tc2_4_1_valid_creation(self) -> None:
        """TC-2.4.1：正常创建"""
        from app.hub.events.types import DiscussionMessageCreatedPayload

        payload = DiscussionMessageCreatedPayload(thread_id="t-1", content="hello")
        assert payload.thread_id == "t-1"
        assert payload.content == "hello"
        assert payload.request_summary is False

    def test_tc2_4_1_thread_id_required(self) -> None:
        """TC-2.4.1：thread_id缺失报错"""
        from app.hub.events.types import DiscussionMessageCreatedPayload

        with pytest.raises(ValidationError):
            DiscussionMessageCreatedPayload(content="hello")  # type: ignore[call-arg]

    def test_tc2_4_1_content_required(self) -> None:
        """TC-2.4.1：content缺失报错"""
        from app.hub.events.types import DiscussionMessageCreatedPayload

        with pytest.raises(ValidationError):
            DiscussionMessageCreatedPayload(thread_id="t-1")  # type: ignore[call-arg]

    def test_tc2_4_1_content_non_str_type(self) -> None:
        """TC-2.4.1：content非str类型报错"""
        from app.hub.events.types import DiscussionMessageCreatedPayload

        with pytest.raises(ValidationError):
            DiscussionMessageCreatedPayload(thread_id="t-1", content=123)  # type: ignore[arg-type]

    def test_tc2_4_1_request_summary_default_false(self) -> None:
        """TC-2.4.1：request_summary默认false"""
        from app.hub.events.types import DiscussionMessageCreatedPayload

        payload = DiscussionMessageCreatedPayload(thread_id="t-1", content="hello")
        assert payload.request_summary is False


class TestDiscussionSummaryGeneratedPayload:
    """TC-2.4.2：DiscussionSummaryGenerated payload"""

    def test_tc2_4_2_valid_creation(self) -> None:
        """TC-2.4.2：正常创建"""
        from app.hub.events.types import DiscussionSummaryGeneratedPayload

        payload = DiscussionSummaryGeneratedPayload(
            thread_id="t-1",
            summary_id="s-1",
            consensus_points=["共识1"],
            divergence_points=["分歧1"],
            action_items=["行动1"],
            knowledge_references=["k-1"],
        )
        assert payload.thread_id == "t-1"
        assert payload.consensus_points == ["共识1"]

    def test_tc2_4_2_consensus_points_required(self) -> None:
        """TC-2.4.2：consensus_points缺失报错"""
        from app.hub.events.types import DiscussionSummaryGeneratedPayload

        with pytest.raises(ValidationError):
            DiscussionSummaryGeneratedPayload(  # type: ignore[call-arg]
                thread_id="t-1",
                summary_id="s-1",
                divergence_points=["分歧1"],
                action_items=["行动1"],
                knowledge_references=["k-1"],
            )

    def test_tc2_4_2_list_int_type_error(self) -> None:
        """TC-2.4.2：传入list[int]类型报错"""
        from app.hub.events.types import DiscussionSummaryGeneratedPayload

        with pytest.raises(ValidationError):
            DiscussionSummaryGeneratedPayload(
                thread_id="t-1",
                summary_id="s-1",
                consensus_points=[1, 2],  # type: ignore[list-item]
                divergence_points=[3],  # type: ignore[list-item]
                action_items=[4],  # type: ignore[list-item]
                knowledge_references=["k-1"],
            )


class TestExecutionPlanProposedPayload:
    """TC-2.4.3：ExecutionPlanProposed payload"""

    def test_tc2_4_3_valid_creation(self) -> None:
        """TC-2.4.3：正常创建"""
        from app.hub.events.types import ExecutionPlanProposedPayload, PlanTaskItem

        payload = ExecutionPlanProposedPayload(
            plan_id="p-1",
            thread_id="t-1",
            tasks=[
                PlanTaskItem(
                    task_id="task-1",
                    type="code",
                    description="实现功能",
                    dependencies=[],
                    priority="high",
                )
            ],
        )
        assert payload.plan_id == "p-1"

    def test_tc2_4_3_plan_id_required(self) -> None:
        """TC-2.4.3：plan_id缺失报错"""
        from app.hub.events.types import ExecutionPlanProposedPayload, PlanTaskItem

        with pytest.raises(ValidationError):
            ExecutionPlanProposedPayload(  # type: ignore[call-arg]
                thread_id="t-1",
                tasks=[
                    PlanTaskItem(
                        task_id="task-1",
                        type="code",
                        description="实现功能",
                        dependencies=[],
                        priority="high",
                    )
                ],
            )

    def test_tc2_4_3_thread_id_required(self) -> None:
        """TC-2.4.3：thread_id缺失报错"""
        from app.hub.events.types import ExecutionPlanProposedPayload, PlanTaskItem

        with pytest.raises(ValidationError):
            ExecutionPlanProposedPayload(  # type: ignore[call-arg]
                plan_id="p-1",
                tasks=[
                    PlanTaskItem(
                        task_id="task-1",
                        type="code",
                        description="实现功能",
                        dependencies=[],
                        priority="high",
                    )
                ],
            )

    def test_tc2_4_3_task_priority_invalid(self) -> None:
        """TC-2.4.3：priority非法值报错"""
        from app.hub.events.types import PlanTaskItem

        with pytest.raises(ValidationError):
            PlanTaskItem(
                task_id="task-1",
                type="code",
                description="实现功能",
                dependencies=[],
                priority="urgent",  # type: ignore[arg-type]
            )


class TestExecutionPlanApprovedPayload:
    """TC-2.4.4：ExecutionPlanApproved payload"""

    def test_tc2_4_4_valid_creation(self) -> None:
        """TC-2.4.4：正常创建"""
        from app.hub.events.types import ExecutionPlanApprovedPayload

        payload = ExecutionPlanApprovedPayload(plan_id="p-1", approved_tasks=["task-1"])
        assert payload.plan_id == "p-1"
        assert payload.approved_tasks == ["task-1"]
        assert payload.modifications is None

    def test_tc2_4_4_approved_tasks_required(self) -> None:
        """TC-2.4.4：approved_tasks缺失报错"""
        from app.hub.events.types import ExecutionPlanApprovedPayload

        with pytest.raises(ValidationError):
            ExecutionPlanApprovedPayload(plan_id="p-1")  # type: ignore[call-arg]

    def test_tc2_4_4_modifications_optional(self) -> None:
        """TC-2.4.4：modifications选填，默认None"""
        from app.hub.events.types import ExecutionPlanApprovedPayload

        payload = ExecutionPlanApprovedPayload(plan_id="p-1", approved_tasks=["task-1"])
        assert payload.modifications is None

        payload_with_mods = ExecutionPlanApprovedPayload(
            plan_id="p-1",
            approved_tasks=["task-1"],
            modifications={"task-2": {"description": "修改后的描述"}},
        )
        assert payload_with_mods.modifications is not None


class TestExecutionPlanRejectedPayload:
    """TC-2.4.5：ExecutionPlanRejected payload"""

    def test_tc2_4_5_valid_creation(self) -> None:
        """TC-2.4.5：正常创建"""
        from app.hub.events.types import ExecutionPlanRejectedPayload

        payload = ExecutionPlanRejectedPayload(plan_id="p-1", reason="不满意", suggestions=["修改建议1"])
        assert payload.reason == "不满意"

    def test_tc2_4_5_reason_required(self) -> None:
        """TC-2.4.5：reason缺失报错"""
        from app.hub.events.types import ExecutionPlanRejectedPayload

        with pytest.raises(ValidationError):
            ExecutionPlanRejectedPayload(suggestions=["修改建议1"], plan_id="p-1")  # type: ignore[call-arg]

    def test_tc2_4_5_suggestions_required(self) -> None:
        """TC-2.4.5：suggestions缺失报错"""
        from app.hub.events.types import ExecutionPlanRejectedPayload

        with pytest.raises(ValidationError):
            ExecutionPlanRejectedPayload(reason="不满意", plan_id="p-1")  # type: ignore[call-arg]


class TestTaskOutputGeneratedPayload:
    """TC-2.4.6：TaskOutputGenerated payload"""

    def test_tc2_4_6_valid_creation(self) -> None:
        """TC-2.4.6：正常创建"""
        from app.hub.events.types import TaskOutputGeneratedPayload

        payload = TaskOutputGeneratedPayload(
            task_id="task-1",
            plan_id="p-1",
            output_id="o-1",
            output_type="code",
            content="代码内容",
        )
        assert payload.task_id == "task-1"
        assert payload.output_type == "code"
        assert payload.diff is None

    def test_tc2_4_6_required_fields(self) -> None:
        """TC-2.4.6：task_id/plan_id/output_id/output_type/content必填"""
        from app.hub.events.types import TaskOutputGeneratedPayload

        with pytest.raises(ValidationError):
            TaskOutputGeneratedPayload(  # type: ignore[call-arg]
                output_type="code",
                content="内容",
            )

    def test_tc2_4_6_output_type_invalid(self) -> None:
        """TC-2.4.6：output_type非法值报错"""
        from app.hub.events.types import TaskOutputGeneratedPayload

        with pytest.raises(ValidationError):
            TaskOutputGeneratedPayload(
                task_id="task-1",
                plan_id="p-1",
                output_id="o-1",
                output_type="image",  # type: ignore[arg-type]
                content="内容",
            )

    def test_tc2_4_6_diff_optional(self) -> None:
        """TC-2.4.6：diff选填（output_type=code时）"""
        from app.hub.events.types import TaskOutputGeneratedPayload

        payload = TaskOutputGeneratedPayload(
            task_id="task-1",
            plan_id="p-1",
            output_id="o-1",
            output_type="code",
            content="代码内容",
            diff="diff内容",
        )
        assert payload.diff == "diff内容"

    def test_tc2_4_6_file_paths_optional(self) -> None:
        """TC-2.4.6：file_paths选填"""
        from app.hub.events.types import TaskOutputGeneratedPayload

        payload = TaskOutputGeneratedPayload(
            task_id="task-1",
            plan_id="p-1",
            output_id="o-1",
            output_type="code",
            content="代码内容",
            file_paths=["src/main.py"],
        )
        assert payload.file_paths == ["src/main.py"]


class TestTaskOutputApprovedPayload:
    """TC-2.4.7：TaskOutputApproved payload"""

    def test_tc2_4_7_valid_creation(self) -> None:
        """TC-2.4.7：正常创建"""
        from app.hub.events.types import TaskOutputApprovedPayload

        payload = TaskOutputApprovedPayload(output_id="o-1")
        assert payload.output_id == "o-1"
        assert payload.feedback is None

    def test_tc2_4_7_output_id_required(self) -> None:
        """TC-2.4.7：output_id必填"""
        from app.hub.events.types import TaskOutputApprovedPayload

        with pytest.raises(ValidationError):
            TaskOutputApprovedPayload()  # type: ignore[call-arg]

    def test_tc2_4_7_feedback_optional(self) -> None:
        """TC-2.4.7：feedback选填，默认None"""
        from app.hub.events.types import TaskOutputApprovedPayload

        payload = TaskOutputApprovedPayload(output_id="o-1", feedback="做得不错")
        assert payload.feedback == "做得不错"


class TestTaskOutputRevisionRequestedPayload:
    """TC-2.4.8：TaskOutputRevisionRequested payload"""

    def test_tc2_4_8_valid_creation(self) -> None:
        """TC-2.4.8：正常创建"""
        from app.hub.events.types import TaskOutputRevisionRequestedPayload

        payload = TaskOutputRevisionRequestedPayload(
            output_id="o-1",
            task_id="task-1",
            issues=["问题1"],
            suggestions=["建议1"],
        )
        assert payload.output_id == "o-1"

    def test_tc2_4_8_required_fields(self) -> None:
        """TC-2.4.8：output_id/task_id/issues/suggestions必填"""
        from app.hub.events.types import TaskOutputRevisionRequestedPayload

        with pytest.raises(ValidationError):
            TaskOutputRevisionRequestedPayload(  # type: ignore[call-arg]
                issues=["问题1"],
                suggestions=["建议1"],
            )

        with pytest.raises(ValidationError):
            TaskOutputRevisionRequestedPayload(  # type: ignore[call-arg]
                output_id="o-1",
                task_id="task-1",
            )
