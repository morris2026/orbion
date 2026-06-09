"""Bitmask权限位与角色映射UT：HumanPermission、AgentPermission、角色映射、compute_permissions"""

from app.hub.permissions.bitmask import AgentPermission, HumanPermission
from app.hub.permissions.compute import compute_permissions
from app.hub.permissions.roles import AGENT_ROLE_BITS, HUMAN_ROLE_BITS


class TestHumanPermissionBitValues:
    """MVP-8.1: HumanPermission位值正确"""

    def test_all_bit_values(self) -> None:
        assert HumanPermission.VIEW_DISCUSSION == 1 << 0
        assert HumanPermission.CREATE_MESSAGE == 1 << 1
        assert HumanPermission.EDIT_OWN_MESSAGE == 1 << 2
        assert HumanPermission.APPROVE_PLAN == 1 << 3
        assert HumanPermission.REJECT_PLAN == 1 << 4
        assert HumanPermission.VIEW_KNOWLEDGE == 1 << 5
        assert HumanPermission.EDIT_KNOWLEDGE == 1 << 6
        assert HumanPermission.MANAGE_MEMBERS == 1 << 7
        assert HumanPermission.MANAGE_AGENTS == 1 << 8
        assert HumanPermission.MANAGE_SPACE == 1 << 9
        assert HumanPermission.MANAGE_PROJECT == 1 << 10
        assert HumanPermission.ADMINISTRATOR == 1 << 11

    def test_member_count(self) -> None:
        assert len(HumanPermission) == 12

    def test_all_bits_sum(self) -> None:
        assert HumanPermission.all_bits() == 4095


class TestAgentPermissionBitValues:
    """MVP-8.2: AgentPermission位值正确"""

    def test_all_bit_values(self) -> None:
        assert AgentPermission.QUERY_KNOWLEDGE == 1 << 0
        assert AgentPermission.READ_DOCUMENT == 1 << 1
        assert AgentPermission.POST_DISCUSSION == 1 << 2
        assert AgentPermission.GENERATE_PLAN == 1 << 3
        assert AgentPermission.GENERATE_CODE == 1 << 4
        assert AgentPermission.GENERATE_DOCUMENT == 1 << 5
        assert AgentPermission.REQUEST_APPROVAL == 1 << 6
        assert AgentPermission.WRITE_KNOWLEDGE == 1 << 7
        assert AgentPermission.DELEGATE_TASK == 1 << 8
        assert AgentPermission.NAVIGATE_LINKS == 1 << 9
        assert AgentPermission.MANAGE_AGENTS == 1 << 10

    def test_member_count(self) -> None:
        assert len(AgentPermission) == 11

    def test_all_bits_sum(self) -> None:
        assert AgentPermission.all_bits() == 2047


class TestHumanRoleMapping:
    """MVP-8.3: 人类角色→权限位映射"""

    def test_owner_role(self) -> None:
        assert HUMAN_ROLE_BITS["owner"] == 4095

    def test_admin_role(self) -> None:
        assert HUMAN_ROLE_BITS["admin"] == 2047

    def test_member_role(self) -> None:
        assert HUMAN_ROLE_BITS["member"] == 31

    def test_viewer_role(self) -> None:
        assert HUMAN_ROLE_BITS["viewer"] == 1


class TestAgentRoleMapping:
    """MVP-8.4: Agent角色→权限位映射"""

    def test_summary_agent(self) -> None:
        assert AGENT_ROLE_BITS["summary"] == 4

    def test_decompose_agent(self) -> None:
        assert AGENT_ROLE_BITS["decompose"] == 76

    def test_execute_agent(self) -> None:
        # GENERATE_CODE(16) + GENERATE_DOCUMENT(32) + REQUEST_APPROVAL(64) = 112
        assert AGENT_ROLE_BITS["execute"] == 112


class TestComputePermissionsDenyOverAllow:
    """MVP-8.5: compute_permissions deny胜过allow"""

    def test_deny_overrides_allow(self) -> None:
        allow = HumanPermission.VIEW_DISCUSSION | HumanPermission.CREATE_MESSAGE
        deny = HumanPermission.VIEW_DISCUSSION
        assert compute_permissions(allow, HumanPermission.VIEW_DISCUSSION, deny) is False


class TestComputePermissionsAllowExists:
    """MVP-8.6: compute_permissions allow位存在"""

    def test_allow_present(self) -> None:
        assert compute_permissions(HumanPermission.all_bits(), HumanPermission.APPROVE_PLAN, 0) is True


class TestComputePermissionsNoAllow:
    """MVP-8.7: compute_permissions无allow位"""

    def test_allow_missing(self) -> None:
        assert compute_permissions(HumanPermission.VIEW_DISCUSSION, HumanPermission.APPROVE_PLAN, 0) is False


class TestAdministratorBypass:
    """MVP-8.10: ADMINISTRATOR位绕过所有权限检查"""

    def test_administrator_passes_any_permission(self) -> None:
        allow = HumanPermission.ADMINISTRATOR
        for perm in HumanPermission:
            assert compute_permissions(allow, perm, 0) is True

    def test_deny_overrides_administrator(self) -> None:
        """Deny胜过Allow也胜过ADMINISTRATOR"""
        allow = HumanPermission.all_bits()
        deny = HumanPermission.MANAGE_MEMBERS
        assert compute_permissions(allow, HumanPermission.MANAGE_MEMBERS, deny) is False
