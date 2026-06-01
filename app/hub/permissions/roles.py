"""角色→权限位映射：4种人类角色、3种Agent角色"""

from app.hub.permissions.bitmask import AgentPermission, HumanPermission

HUMAN_ROLE_BITS: dict[str, int] = {
    "owner": HumanPermission.all_bits(),  # 4095
    "admin": HumanPermission.all_bits() & ~HumanPermission.ADMINISTRATOR,  # 2047
    "member": (
        HumanPermission.VIEW_DISCUSSION
        | HumanPermission.CREATE_MESSAGE
        | HumanPermission.EDIT_OWN_MESSAGE
        | HumanPermission.APPROVE_PLAN
        | HumanPermission.REJECT_PLAN
    ),  # 31
    "viewer": HumanPermission.VIEW_DISCUSSION,  # 1
}

AGENT_ROLE_BITS: dict[str, int] = {
    "summary": AgentPermission.POST_DISCUSSION,  # 4
    "decompose": (
        AgentPermission.POST_DISCUSSION | AgentPermission.GENERATE_PLAN | AgentPermission.REQUEST_APPROVAL
    ),  # 76
    "execute": (
        AgentPermission.GENERATE_CODE | AgentPermission.GENERATE_DOCUMENT | AgentPermission.REQUEST_APPROVAL
    ),  # 112
}
