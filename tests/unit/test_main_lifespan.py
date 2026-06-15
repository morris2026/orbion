"""main.py 启动流程验证测试"""

from pathlib import Path

from app.biz.agents.declarations import BUILTIN_AGENT_DECLARATIONS
from app.biz.agents.templates import AgentTemplateManager
from app.config import Settings

JWT_SECRET_TEST = "test-secret-for-main-lifespan"


class TestMvpFl6MainLifespan:
    def test_mvp_fl_6_1_template_files_created_on_startup(self, tmp_path: Path) -> None:
        """MVP-FL-6.1：启动时初始化3个内置Agent模板，模板文件存在"""
        settings = Settings(jwt_secret=JWT_SECRET_TEST, root_dir=str(tmp_path))
        manager = AgentTemplateManager(settings)

        for agent_type, declaration in BUILTIN_AGENT_DECLARATIONS.items():
            manager.ensure_template(agent_type, declaration.model_dump(), "")

        assert (tmp_path / "agents" / "summary" / "declaration.json").exists()
        assert (tmp_path / "agents" / "summary" / "memory.md").exists()
        assert (tmp_path / "agents" / "decompose" / "declaration.json").exists()
        assert (tmp_path / "agents" / "execute" / "declaration.json").exists()
