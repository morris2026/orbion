"""MVP-2.5~MVP-2.8：业务Pydantic模型校验测试"""

import pytest
from pydantic import ValidationError


class TestUserModels:
    """MVP-2.5：User模型校验"""

    def test_tc2_5_user_register_valid(self) -> None:
        """MVP-2.5：正常创建UserRegister"""
        from app.hub.auth.models import UserRegister

        user = UserRegister(username="morris_123", password="password123", display_name="Morris")
        assert user.username == "morris_123"
        assert user.display_name == "Morris"

    def test_tc2_5_username_min_length(self) -> None:
        """MVP-2.5：username长度限制3-32，太短报错"""
        from app.hub.auth.models import UserRegister

        with pytest.raises(ValidationError):
            UserRegister(username="ab", password="password123", display_name="A")

    def test_tc2_5_username_max_length(self) -> None:
        """MVP-2.5：username长度超过32报错"""
        from app.hub.auth.models import UserRegister

        with pytest.raises(ValidationError):
            UserRegister(
                username="a" * 33,
                password="password123",
                display_name="Morris",
            )

    def test_tc2_5_username_pattern(self) -> None:
        """MVP-2.5：username pattern限制字母数字下划线，含特殊字符报错"""
        from app.hub.auth.models import UserRegister

        with pytest.raises(ValidationError):
            UserRegister(username="morris-123", password="password123", display_name="Morris")

    def test_tc2_5_password_min_length(self) -> None:
        """MVP-2.5：password最小长度8"""
        from app.hub.auth.models import UserRegister

        with pytest.raises(ValidationError):
            UserRegister(username="morris", password="short", display_name="Morris")

    def test_tc2_5_display_name_min_length(self) -> None:
        """MVP-2.5：display_name最小长度1"""
        from app.hub.auth.models import UserRegister

        with pytest.raises(ValidationError):
            UserRegister(username="morris", password="password123", display_name="")

    def test_tc2_5_display_name_max_length(self) -> None:
        """MVP-2.5：display_name最大长度64"""
        from app.hub.auth.models import UserRegister

        with pytest.raises(ValidationError):
            UserRegister(username="morris", password="password123", display_name="M" * 65)

    def test_tc2_5_user_login_valid(self) -> None:
        """MVP-2.5：正常创建UserLogin"""
        from app.hub.auth.models import UserLogin

        login = UserLogin(username="morris", password="password123")
        assert login.username == "morris"

    def test_tc2_5_user_response_valid(self) -> None:
        """MVP-2.5：正常创建UserResponse"""
        from app.hub.auth.models import UserResponse

        resp = UserResponse(
            user_id="uid-1",
            username="morris",
            display_name="Morris",
            access_token="token-1",
        )
        assert resp.token_type == "bearer"


class TestProjectMemberThreadMessageModels:
    """MVP-2.6：Project/Member/Thread/Message模型校验"""

    def test_tc2_6_project_create_valid(self) -> None:
        """MVP-2.6：正常创建ProjectCreate"""
        from app.biz.projects.models import ProjectCreate

        pc = ProjectCreate(name="我的项目")
        assert pc.name == "我的项目"
        assert pc.description is None

    def test_tc2_6_project_create_name_required(self) -> None:
        """MVP-2.6：ProjectCreate name必填"""
        from app.biz.projects.models import ProjectCreate

        with pytest.raises(ValidationError):
            ProjectCreate()  # type: ignore[call-arg]

    def test_tc2_6_project_create_name_length(self) -> None:
        """MVP-2.6：ProjectCreate name长度限制1-128"""
        from app.biz.projects.models import ProjectCreate

        with pytest.raises(ValidationError):
            ProjectCreate(name="")

        with pytest.raises(ValidationError):
            ProjectCreate(name="x" * 129)

    def test_tc2_6_project_response_valid(self) -> None:
        """MVP-2.6：正常创建ProjectResponse"""
        from datetime import datetime

        from app.biz.projects.models import ProjectResponse

        resp = ProjectResponse(
            id="p-1",
            name="项目",
            description="描述",
            tenant_id="default",
            created_at=datetime.now(),
        )
        assert resp.tenant_id == "default"

    def test_tc2_6_member_add_valid(self) -> None:
        """MVP-2.6：正常创建MemberAdd"""
        from app.biz.projects.models import MemberAdd

        ma = MemberAdd(user_id="u-1", role="member")
        assert ma.role == "member"

    def test_tc2_6_member_response_valid(self) -> None:
        """MVP-2.6：正常创建MemberResponse"""
        from app.biz.projects.models import MemberResponse

        mr = MemberResponse(
            participant_id="u-1",
            project_id="p-1",
            type="human",
            display_name="Morris",
            role="owner",
        )
        assert mr.type == "human"

    def test_tc2_6_thread_create_valid(self) -> None:
        """MVP-2.6：正常创建ThreadCreate"""
        from app.biz.threads.models import ThreadCreate

        tc = ThreadCreate(title="讨论主题")
        assert tc.title == "讨论主题"
        assert tc.type == "discussion"

    def test_tc2_6_thread_create_title_max_length(self) -> None:
        """MVP-2.6：ThreadCreate title长度限制1-256"""
        from app.biz.threads.models import ThreadCreate

        with pytest.raises(ValidationError):
            ThreadCreate(title="x" * 257)

    def test_tc2_6_thread_create_type_default(self) -> None:
        """MVP-2.6：ThreadCreate.type默认discussion"""
        from app.biz.threads.models import ThreadCreate

        tc = ThreadCreate(title="讨论主题")
        assert tc.type == "discussion"

    def test_tc2_6_thread_response_valid(self) -> None:
        """MVP-2.6：正常创建ThreadResponse"""
        from datetime import datetime

        from app.biz.threads.models import ThreadResponse

        tr = ThreadResponse(
            id="t-1",
            project_id="p-1",
            title="讨论主题",
            status="active",
            type="discussion",
            created_at=datetime.now(),
        )
        assert tr.status == "active"

    def test_tc2_6_message_create_valid(self) -> None:
        """MVP-2.6：正常创建MessageCreate"""
        from app.biz.threads.models import MessageCreate

        mc = MessageCreate(content="消息内容")
        assert mc.content == "消息内容"
        assert mc.request_summary is False

    def test_tc2_6_message_create_request_summary_default(self) -> None:
        """MVP-2.6：MessageCreate.request_summary默认false"""
        from app.biz.threads.models import MessageCreate

        mc = MessageCreate(content="消息内容")
        assert mc.request_summary is False

    def test_tc2_6_message_create_content_length(self) -> None:
        """MVP-2.6：MessageCreate content长度限制1-10000，边界值验证"""
        from app.biz.threads.models import MessageCreate

        # 边界值有效
        mc_min = MessageCreate(content="x")
        assert len(mc_min.content) == 1
        mc_max = MessageCreate(content="x" * 10000)
        assert len(mc_max.content) == 10000

        # 超出边界无效
        with pytest.raises(ValidationError):
            MessageCreate(content="")

        with pytest.raises(ValidationError):
            MessageCreate(content="x" * 10001)


class TestPlanOutputModels:
    """MVP-2.7：PlanTask/PlanResponse/OutputResponse模型校验"""

    def test_tc2_7_plan_task_valid(self) -> None:
        """MVP-2.7：正常创建PlanTask"""
        from app.biz.plans.models import PlanTask

        pt = PlanTask(
            task_id="task-1",
            type="code",
            description="实现功能",
            priority="high",
        )
        assert pt.status == "pending"
        assert pt.dependencies == []

    def test_tc2_7_plan_task_status_default(self) -> None:
        """MVP-2.7：PlanTask.status默认pending"""
        from app.biz.plans.models import PlanTask

        pt = PlanTask(
            task_id="task-1",
            type="code",
            description="实现功能",
            priority="high",
        )
        assert pt.status == "pending"

    def test_tc2_7_plan_approve_modifications_optional(self) -> None:
        """MVP-2.7：PlanApprove.modifications可选"""
        from app.biz.plans.models import PlanApprove

        pa = PlanApprove(approved_tasks=["task-1"])
        assert pa.modifications is None

    def test_tc2_7_plan_reject_valid(self) -> None:
        """MVP-2.7：正常创建PlanReject"""
        from app.biz.plans.models import PlanReject

        pr = PlanReject(reason="不满意")
        assert pr.reason == "不满意"
        assert pr.suggestions == []

    def test_tc2_7_output_response_valid(self) -> None:
        """MVP-2.7：正常创建OutputResponse"""
        from datetime import datetime

        from app.biz.outputs.models import OutputResponse

        or_ = OutputResponse(
            id="o-1",
            task_id="task-1",
            plan_id="p-1",
            output_type="code",
            content="内容",
            status="generated",
            version=1,
            created_at=datetime.now(),
        )
        assert or_.diff is None
        assert or_.file_paths == []

    def test_tc2_7_output_response_diff_optional(self) -> None:
        """MVP-2.7：OutputResponse.diff可选"""
        from datetime import datetime

        from app.biz.outputs.models import OutputResponse

        or_ = OutputResponse(
            id="o-1",
            task_id="task-1",
            plan_id="p-1",
            output_type="code",
            content="内容",
            diff="diff内容",
            status="generated",
            version=1,
            created_at=datetime.now(),
        )
        assert or_.diff == "diff内容"

    def test_tc2_7_output_approve_feedback_optional(self) -> None:
        """MVP-2.7：OutputApprove.feedback可选"""
        from app.biz.outputs.models import OutputApprove

        oa = OutputApprove()
        assert oa.feedback is None

    def test_tc2_7_output_request_revision_valid(self) -> None:
        """MVP-2.7：正常创建OutputRequestRevision"""
        from app.biz.outputs.models import OutputRequestRevision

        orr = OutputRequestRevision(issues=["问题1"])
        assert orr.issues == ["问题1"]
        assert orr.suggestions == []


class TestAgentModels:
    """MVP-2.8：Agent模型校验"""

    def test_tc2_8_agent_create_valid(self) -> None:
        """MVP-2.8：正常创建AgentCreate"""
        from app.biz.agents.models import AgentCreate

        ac = AgentCreate(agent_type="summary", model_id="claude-haiku-4-5-20251001", display_name="总结Agent")
        assert ac.agent_type == "summary"

    def test_tc2_8_agent_create_type_limited(self) -> None:
        """MVP-2.8：AgentCreate.agent_type限定summary/decompose/execute"""
        from app.biz.agents.models import AgentCreate

        with pytest.raises(ValidationError):
            AgentCreate(agent_type="other", model_id="claude", display_name="Agent")  # type: ignore[arg-type]

    def test_tc2_8_agent_response_status_literal(self) -> None:
        """MVP-2.8：AgentResponse.status限定idle/running/error"""
        from app.biz.agents.models import AgentResponse

        with pytest.raises(ValidationError):
            AgentResponse(
                participant_id="a-1",
                project_id="p-1",
                display_name="Agent",
                agent_type="summary",
                model_id="claude",
                status="unknown",  # type: ignore[arg-type]
                subscribed_events=["DiscussionMessageCreated"],
                roles=4,
            )

    def test_tc2_8_agent_status_status_literal(self) -> None:
        """MVP-2.8：AgentStatus.status限定idle/running/error"""
        from app.biz.agents.models import AgentStatus

        with pytest.raises(ValidationError):
            AgentStatus(
                agent_id="a-1",
                status="unknown",  # type: ignore[arg-type]
                completed_count=0,
                error_count=0,
            )

    def test_tc2_8_agent_response_subscribed_events_list(self) -> None:
        """MVP-2.8：AgentResponse.subscribed_events为列表"""
        from app.biz.agents.models import AgentResponse

        ar = AgentResponse(
            participant_id="a-1",
            project_id="p-1",
            display_name="总结Agent",
            agent_type="summary",
            model_id="claude-haiku-4-5-20251001",
            status="idle",
            subscribed_events=["DiscussionMessageCreated"],
            roles=4,
        )
        assert isinstance(ar.subscribed_events, list)

    def test_tc2_8_agent_status_current_task_optional(self) -> None:
        """MVP-2.8：AgentStatus.current_task可选"""

        from app.biz.agents.models import AgentStatus

        as_ = AgentStatus(
            agent_id="a-1",
            status="idle",
            completed_count=0,
            error_count=0,
        )
        assert as_.current_task is None
        assert as_.last_execution_at is None
