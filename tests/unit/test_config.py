"""MVP-1.1~MVP-1.3：FastAPI应用启动与Settings配置测试"""

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

import pytest
from pytest import MonkeyPatch

from app.config import OrbionConfigSchema, PostgresConfigSchema, Settings, get_settings
from tests.conftest import JWT_SECRET_TEST


def test_tc1_1_app_exists_and_title() -> None:
    """MVP-1.1：导入app.main模块，app对象存在，app.title为Orbion MVP"""
    from app.main import app

    assert app is not None
    assert app.title == "Orbion MVP"


def test_tc1_2_settings_defaults() -> None:
    """MVP-1.2：Settings默认值和环境变量覆盖正确

    conftest的_inject_test_env_vars注入ORBION_POSTGRES__DB=orbion_test，
    测试不应硬编码断言默认值，而是验证Settings正确反映当前环境。
    """
    s = get_settings()
    expected_db = os.environ.get("ORBION_POSTGRES__DB", "orbion")
    expected_url = f"postgresql://orbion:orbion_dev@localhost:5432/{expected_db}"
    assert s.postgres.db == expected_db
    assert s.postgres.url == expected_url


def test_tc1_3_settings_env_override(monkeypatch: MonkeyPatch) -> None:
    """MVP-1.3：环境变量覆盖Settings对应字段"""
    monkeypatch.setenv("ORBION_POSTGRES__HOST", "testhost")
    monkeypatch.setenv("ORBION_POSTGRES__PORT", "5433")
    monkeypatch.setenv("ORBION_POSTGRES__DB", "testdb")
    monkeypatch.setenv("ORBION_POSTGRES__USER", "testuser")
    monkeypatch.setenv("ORBION_POSTGRES__PASSWORD", "testpass")
    monkeypatch.setenv("ORBION_JWT_SECRET", JWT_SECRET_TEST)
    monkeypatch.setenv("ORBION_ANTHROPIC_API_KEY", "sk-test-key")
    monkeypatch.setenv("ORBION_ROOT_DIR", "/var/lib/orbion")

    s = get_settings()
    assert s.postgres.url == "postgresql://testuser:testpass@testhost:5433/testdb"
    assert s.jwt_secret == JWT_SECRET_TEST
    assert s.anthropic_api_key == "sk-test-key"
    assert s.root_dir == "/var/lib/orbion"
    assert not hasattr(s, "repo_path")
    assert not hasattr(s, "memory_base_path")


def test_orbion_config_schema_forbid_secrets() -> None:
    """OrbionConfigSchema extra='forbid' 阻止密钥字段出现在配置中"""
    with pytest.raises(Exception, match="Extra inputs are not permitted"):
        OrbionConfigSchema.model_validate({"jwt_secret": JWT_SECRET_TEST})
    with pytest.raises(Exception, match="Extra inputs are not permitted"):
        OrbionConfigSchema.model_validate({"anthropic_api_key": "sk-key"})


def test_postgres_config_schema_forbid_password() -> None:
    """PostgresConfigSchema extra='forbid' 阻止密码出现在外部配置中"""
    with pytest.raises(Exception, match="Extra inputs are not permitted"):
        PostgresConfigSchema.model_validate({"password": "secret"})


def test_orbion_config_schema_defaults() -> None:
    """OrbionConfigSchema 空输入返回完整默认值"""
    config = OrbionConfigSchema.model_validate({})
    assert config.database == "postgres"
    assert config.postgres.host == "localhost"
    assert config.postgres.port == 5432
    assert config.root_dir == "./data"
    assert not hasattr(config, "repo_path")
    assert not hasattr(config, "memory_base_path")


def test_config_file_parser_no_file_fallback(monkeypatch: MonkeyPatch) -> None:
    """无配置文件时回退到 OrbionConfigSchema 默认值，database 展开为4个字段"""
    from app.config import OrbionConfigFileParser

    monkeypatch.setenv("ORBION_CONFIG_PATH", "/nonexistent/orbion.json")
    source = OrbionConfigFileParser(Settings)
    data = source()
    assert data["postgres"]["host"] == "localhost"
    assert data["event_store"] == "postgres"
    assert "database" not in data


def test_config_file_parser_expands_database(monkeypatch: MonkeyPatch) -> None:
    """OrbionConfigFileParser 将 database 展开为4个per-feature字段"""
    from app.config import OrbionConfigFileParser

    with NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump({"database": "postgres"}, f)
        f.flush()
        config_path = f.name

    monkeypatch.setenv("ORBION_CONFIG_PATH", config_path)
    source = OrbionConfigFileParser(Settings)
    data = source()
    assert data["event_store"] == "postgres"
    assert data["event_projections"] == "postgres"
    assert data["project_read"] == "postgres"
    assert data["user_repo"] == "postgres"
    assert "database" not in data
    Path(config_path).unlink()


def test_config_file_parser_reads_file(monkeypatch: MonkeyPatch) -> None:
    """配置文件存在时正确加载并校验"""
    from app.config import OrbionConfigFileParser

    with NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump({"postgres": {"host": "custom-host", "port": 5433}}, f)
        f.flush()
        config_path = f.name

    monkeypatch.setenv("ORBION_CONFIG_PATH", config_path)
    source = OrbionConfigFileParser(Settings)
    data = source()
    assert data["postgres"]["host"] == "custom-host"
    assert data["postgres"]["port"] == 5433
    assert data["postgres"]["db"] == "orbion"  # 默认值填充
    Path(config_path).unlink()


class TestMvpFl1Settings:
    """MVP-FL-1.1~1.7：Settings orbion_dir 替代双路径"""

    def test_mvp_fl_1_1_default_root_dir(self, monkeypatch: MonkeyPatch) -> None:
        """MVP-FL-1.1：Settings 默认 root_dir 为 ./data"""
        monkeypatch.delenv("ORBION_ROOT_DIR", raising=False)
        s = Settings(jwt_secret=JWT_SECRET_TEST)
        assert s.root_dir == "./data"
        assert not hasattr(s, "repo_path")
        assert not hasattr(s, "memory_base_path")

    def test_mvp_fl_1_2_env_override(self, monkeypatch: MonkeyPatch) -> None:
        """MVP-FL-1.2：ORBION_ROOT_DIR 环境变量覆盖"""
        monkeypatch.setenv("ORBION_ROOT_DIR", "/var/lib/orbion")
        s = Settings(jwt_secret=JWT_SECRET_TEST)
        assert s.root_dir == "/var/lib/orbion"

    def test_mvp_fl_1_3_derived_paths_default(self, monkeypatch: MonkeyPatch) -> None:
        """MVP-FL-1.3：派生路径计算 — 默认值"""
        monkeypatch.delenv("ORBION_ROOT_DIR", raising=False)
        s = Settings(jwt_secret=JWT_SECRET_TEST)
        assert s.projects_dir == Path("./data/projects")
        assert s.platform_memory_path == Path("./data/memory.md")
        assert s.project_dir("p1") == Path("./data/projects/p1")
        assert s.project_memory_path("p1") == Path("./data/projects/p1/memory.md")
        assert s.agent_memory_path("p1", "summary") == Path("./data/projects/p1/agents/summary/memory.md")
        assert s.project_repo_path("p1", "orbion") == Path("./data/projects/p1/repo/orbion")
        assert s.thread_dir("p1", "t1") == Path("./data/projects/p1/threads/t1")
        assert s.output_payload_path("p1", "o1") == Path("./data/projects/p1/outputs/o1.json")

    def test_mvp_fl_1_4_derived_paths_absolute(self, monkeypatch: MonkeyPatch) -> None:
        """MVP-FL-1.4：派生路径计算 — 绝对路径"""
        monkeypatch.setenv("ORBION_ROOT_DIR", "/var/lib/orbion")
        s = Settings(jwt_secret=JWT_SECRET_TEST)
        assert s.projects_dir == Path("/var/lib/orbion/projects")
        assert s.platform_memory_path == Path("/var/lib/orbion/memory.md")
        assert s.project_dir("p1") == Path("/var/lib/orbion/projects/p1")
        assert s.project_memory_path("p1") == Path("/var/lib/orbion/projects/p1/memory.md")
        assert s.agent_memory_path("p1", "summary") == Path("/var/lib/orbion/projects/p1/agents/summary/memory.md")
        assert s.project_repo_path("p1", "orbion") == Path("/var/lib/orbion/projects/p1/repo/orbion")
        assert s.thread_dir("p1", "t1") == Path("/var/lib/orbion/projects/p1/threads/t1")
        assert s.output_payload_path("p1", "o1") == Path("/var/lib/orbion/projects/p1/outputs/o1.json")

    def test_mvp_fl_1_5_config_file_new_format(self, monkeypatch: MonkeyPatch) -> None:
        """MVP-FL-1.5：orbion.json 解析新格式"""
        with NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"root_dir": "./custom"}, f)
            f.flush()
            config_path = f.name

        monkeypatch.setenv("ORBION_CONFIG_PATH", config_path)
        s = Settings(jwt_secret=JWT_SECRET_TEST)
        assert s.root_dir == "./custom"
        Path(config_path).unlink()

    def test_mvp_fl_1_6_config_file_old_format_rejected(self) -> None:
        """MVP-FL-1.6：重构后 OrbionConfigSchema 不再包含 repo_path，旧格式报错"""
        with pytest.raises(Exception, match="Extra inputs are not permitted"):
            OrbionConfigSchema.model_validate({"repo_path": "./repo"})

    def test_mvp_fl_1_7_parser_expands_root_dir(self, monkeypatch: MonkeyPatch) -> None:
        """MVP-FL-1.7：OrbionConfigFileParser 展开 root_dir"""
        from app.config import OrbionConfigFileParser

        with NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"root_dir": "./custom"}, f)
            f.flush()
            config_path = f.name

        monkeypatch.setenv("ORBION_CONFIG_PATH", config_path)
        source = OrbionConfigFileParser(Settings)
        data = source()
        assert data["root_dir"] == "./custom"
        Path(config_path).unlink()
