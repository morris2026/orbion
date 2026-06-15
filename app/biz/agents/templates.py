"""AgentTemplateManager——Agent 模板创建与项目实例拷贝"""

import json
import logging
from pathlib import Path
from typing import Any

from app.config import Settings

logger = logging.getLogger(__name__)


class AgentTemplateManager:
    """管理平台级 Agent 模板（agents/<type>/）和项目实例拷贝"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _template_dir(self, agent_type: str) -> Path:
        return Path(self._settings.root_dir) / "agents" / agent_type

    def ensure_template(self, agent_type: str, declaration_dict: dict[str, Any], default_memory: str) -> None:
        """创建 Agent 模板：declaration.json + memory.md。文件已存在则跳过不覆盖"""
        template_dir = self._template_dir(agent_type)
        decl_path = template_dir / "declaration.json"
        mem_path = template_dir / "memory.md"
        if decl_path.exists() and mem_path.exists():
            return
        template_dir.mkdir(parents=True, exist_ok=True)
        if not decl_path.exists():
            decl_path.write_text(json.dumps(declaration_dict, ensure_ascii=False, indent=2), encoding="utf-8")
        if not mem_path.exists():
            mem_path.write_text(default_memory, encoding="utf-8")

    def copy_to_project(self, agent_type: str, project_id: str) -> None:
        """将模板 memory.md 拷贝到项目实例。模板不存在或项目已有则跳过"""
        template_mem = self._template_dir(agent_type) / "memory.md"
        if not template_mem.exists():
            return
        proj_mem = self._settings.agent_memory_path(project_id, agent_type)
        if proj_mem.exists():
            return
        proj_mem.parent.mkdir(parents=True, exist_ok=True)
        proj_mem.write_text(template_mem.read_text(encoding="utf-8"), encoding="utf-8")
