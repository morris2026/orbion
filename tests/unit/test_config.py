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
    monkeypatch.setenv("ORBION_REPO_PATH", "/tmp/repo")
    monkeypatch.setenv("ORBION_MEMORY_BASE_PATH", "/tmp/memory")

    s = get_settings()
    assert s.postgres.url == "postgresql://testuser:testpass@testhost:5433/testdb"
    assert s.jwt_secret == JWT_SECRET_TEST
    assert s.anthropic_api_key == "sk-test-key"
    assert s.repo_path == "/tmp/repo"
    assert s.memory_base_path == "/tmp/memory"


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
