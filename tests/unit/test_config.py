"""TC-1.1~TC-1.3：FastAPI应用启动与Settings配置测试"""

import sys

from pytest import MonkeyPatch


def test_tc1_1_app_exists_and_title() -> None:
    """TC-1.1：导入app.main模块，app对象存在，app.title为Orbion MVP"""
    from app.main import app

    assert app is not None
    assert app.title == "Orbion MVP"


def test_tc1_2_settings_defaults() -> None:
    """TC-1.2：无环境变量时Settings默认值正确"""
    from app.config import Settings

    s = Settings()
    assert s.postgres_url == "postgresql://orbion:orbion_dev@localhost:5432/orbion"
    assert s.jwt_secret == "orbion-dev-secret"
    assert s.anthropic_api_key == ""
    assert s.repo_path == "./repo"
    assert s.memory_base_path == "./data/memory"


def test_tc1_3_settings_env_override(monkeypatch: MonkeyPatch) -> None:
    """TC-1.3：环境变量覆盖Settings对应字段"""
    monkeypatch.setenv("ORBION_POSTGRES_URL", "postgresql://test:test@localhost:5432/testdb")
    monkeypatch.setenv("ORBION_JWT_SECRET", "my-secret")
    monkeypatch.setenv("ORBION_ANTHROPIC_API_KEY", "sk-test-key")
    monkeypatch.setenv("ORBION_REPO_PATH", "/tmp/repo")
    monkeypatch.setenv("ORBION_MEMORY_BASE_PATH", "/tmp/memory")

    # 清除模块缓存，确保环境变量在构造时生效
    sys.modules.pop("app.config", None)
    from app.config import Settings

    s = Settings()
    assert s.postgres_url == "postgresql://test:test@localhost:5432/testdb"
    assert s.jwt_secret == "my-secret"
    assert s.anthropic_api_key == "sk-test-key"
    assert s.repo_path == "/tmp/repo"
    assert s.memory_base_path == "/tmp/memory"
