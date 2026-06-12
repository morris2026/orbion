"""Bitmask权限位定义：人类12位、Agent11位"""

from enum import Enum


class HumanPermission(int, Enum):
    VIEW_DISCUSSION = 1 << 0
    CREATE_MESSAGE = 1 << 1
    EDIT_OWN_MESSAGE = 1 << 2
    APPROVE_PLAN = 1 << 3
    REJECT_PLAN = 1 << 4
    VIEW_KNOWLEDGE = 1 << 5
    EDIT_KNOWLEDGE = 1 << 6
    MANAGE_MEMBERS = 1 << 7
    MANAGE_AGENTS = 1 << 8
    MANAGE_SPACE = 1 << 9
    MANAGE_PROJECT = 1 << 10
    ADMINISTRATOR = 1 << 11
    DELETE_PROJECT = 1 << 12

    @classmethod
    def all_bits(cls) -> int:
        return sum(member.value for member in cls)


class AgentPermission(int, Enum):
    QUERY_KNOWLEDGE = 1 << 0
    READ_DOCUMENT = 1 << 1
    POST_DISCUSSION = 1 << 2
    GENERATE_PLAN = 1 << 3
    GENERATE_CODE = 1 << 4
    GENERATE_DOCUMENT = 1 << 5
    REQUEST_APPROVAL = 1 << 6
    WRITE_KNOWLEDGE = 1 << 7
    DELEGATE_TASK = 1 << 8
    NAVIGATE_LINKS = 1 << 9
    MANAGE_AGENTS = 1 << 10

    @classmethod
    def all_bits(cls) -> int:
        return sum(member.value for member in cls)
