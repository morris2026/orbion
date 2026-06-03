"""SkillDeclaration数据结构定义"""

from typing import Any

from pydantic import BaseModel


class SkillDeclaration(BaseModel):
    """Agent Skill声明——描述Agent的能力单元"""

    name: str
    description: str
    input_schema: dict[str, Any] = {}
    output_schema: dict[str, Any] = {}
    risk_level: str = "low"
    requires_approval: bool = False
