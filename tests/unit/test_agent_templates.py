"""Agent 模板机制测试"""

import json
from pathlib import Path

from app.biz.agents.declarations import BUILTIN_AGENT_DECLARATIONS
from app.biz.agents.templates import AgentTemplateManager
from app.config import Settings

JWT_SECRET_TEST = "test-secret-for-agent-template-tests"


def _make_settings(tmp_path: Path) -> Settings:
    return Settings(jwt_secret=JWT_SECRET_TEST, root_dir=str(tmp_path))


class TestMvpFl4AgentTemplate:
    def test_mvp_fl_4_1_create_template(self, tmp_path: Path) -> None:
        """MVP-FL-4.1：ensure_template 创建模板文件"""
        settings = _make_settings(tmp_path)
        manager = AgentTemplateManager(settings)
        declaration_dict = BUILTIN_AGENT_DECLARATIONS["summary"].model_dump()

        manager.ensure_template("summary", declaration_dict, "默认记忆")

        template_dir = tmp_path / "agents" / "summary"
        decl_path = template_dir / "declaration.json"
        mem_path = template_dir / "memory.md"
        assert decl_path.exists()
        assert json.loads(decl_path.read_text(encoding="utf-8"))["agent_type"] == "summary"
        assert mem_path.exists()
        assert mem_path.read_text(encoding="utf-8") == "默认记忆"

    def test_mvp_fl_4_2_idempotent_ensure_template(self, tmp_path: Path) -> None:
        """MVP-FL-4.2：重复 ensure_template 不覆盖已有模板"""
        settings = _make_settings(tmp_path)
        manager = AgentTemplateManager(settings)
        declaration_dict = BUILTIN_AGENT_DECLARATIONS["summary"].model_dump()

        manager.ensure_template("summary", declaration_dict, "旧记忆")
        manager.ensure_template("summary", declaration_dict, "新记忆")

        mem_path = tmp_path / "agents" / "summary" / "memory.md"
        assert mem_path.read_text(encoding="utf-8") == "旧记忆"

    def test_mvp_fl_4_3_copy_to_project(self, tmp_path: Path) -> None:
        """MVP-FL-4.3：模板拷贝到项目，内容一致"""
        settings = _make_settings(tmp_path)
        manager = AgentTemplateManager(settings)
        declaration_dict = BUILTIN_AGENT_DECLARATIONS["summary"].model_dump()

        manager.ensure_template("summary", declaration_dict, "模板记忆")
        project_dir = settings.project_dir("p1")
        project_dir.mkdir(parents=True, exist_ok=True)

        manager.copy_to_project("summary", "p1")

        proj_mem = settings.agent_memory_path("p1", "summary")
        assert proj_mem.exists()
        assert proj_mem.read_text(encoding="utf-8") == "模板记忆"

    def test_mvp_fl_4_4_project_memory_not_overwritten(self, tmp_path: Path) -> None:
        """MVP-FL-4.4：项目已有 memory.md 时不覆盖"""
        settings = _make_settings(tmp_path)
        manager = AgentTemplateManager(settings)
        declaration_dict = BUILTIN_AGENT_DECLARATIONS["summary"].model_dump()

        manager.ensure_template("summary", declaration_dict, "模板记忆")
        proj_mem = settings.agent_memory_path("p1", "summary")
        proj_mem.parent.mkdir(parents=True, exist_ok=True)
        proj_mem.write_text("项目自定义记忆", encoding="utf-8")

        manager.copy_to_project("summary", "p1")

        assert proj_mem.read_text(encoding="utf-8") == "项目自定义记忆"

    def test_mvp_fl_4_5_missing_template_noop(self, tmp_path: Path) -> None:
        """MVP-FL-4.5：模板不存在时不拷贝、不抛异常"""
        settings = _make_settings(tmp_path)
        manager = AgentTemplateManager(settings)

        project_dir = settings.project_dir("p1")
        project_dir.mkdir(parents=True, exist_ok=True)

        manager.copy_to_project("custom", "p1")

        assert not (settings.agent_memory_path("p1", "custom")).exists()

    def test_mvp_fl_4_6_template_update_no_impact(self, tmp_path: Path) -> None:
        """MVP-FL-4.6：模板更新不影响已注册 Agent"""
        settings = _make_settings(tmp_path)
        manager = AgentTemplateManager(settings)
        declaration_dict = BUILTIN_AGENT_DECLARATIONS["summary"].model_dump()

        manager.ensure_template("summary", declaration_dict, "模板记忆v1")
        project_dir = settings.project_dir("p1")
        project_dir.mkdir(parents=True, exist_ok=True)
        manager.copy_to_project("summary", "p1")

        template_mem = tmp_path / "agents" / "summary" / "memory.md"
        template_mem.write_text("新模板记忆", encoding="utf-8")
        manager.copy_to_project("summary", "p1")

        proj_mem = settings.agent_memory_path("p1", "summary")
        assert proj_mem.read_text(encoding="utf-8") == "模板记忆v1"
