"""Orbion 配置管理：orbion.json（非密钥）+ ORBION_* 环境变量（密钥）"""

import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field
from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict


class PostgresConfigSchema(BaseModel):
    """外部配置校验 schema — 不含密钥，extra="forbid" 拒绝密钥字段"""

    host: str = Field(default="localhost", description="PostgreSQL 主机地址")
    port: int = Field(default=5432, description="PostgreSQL 端口")
    db: str = Field(default="orbion", description="PostgreSQL 数据库名")
    user: str = Field(default="orbion", description="PostgreSQL 用户名")

    model_config = ConfigDict(extra="forbid")


class PostgresSettings(PostgresConfigSchema):
    """运行时配置 — 继承 schema 并加入密钥和连接 URL，自给自足"""

    password: str = Field(default="orbion_dev", description="PostgreSQL 密码，只从环境变量读取")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def url(self) -> str:
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.db}"


class OrbionConfigSchema(BaseModel):
    """外部配置校验 schema

    只允许非密钥字段。密钥（jwt_secret、anthropic_api_key）
    只从 ORBION_* 环境变量读取，不允许出现在配置文件中。
    实现特定配置放在嵌套子模型中，不污染顶层。
    """

    database: str = Field(default="postgres", description="数据库类型，各特性共用")
    postgres: PostgresConfigSchema = Field(
        default_factory=PostgresConfigSchema, description="PostgreSQL 外部配置校验 schema"
    )
    repo_path: str = Field(default="./repo", description="Git 产出存放路径")
    memory_base_path: str = Field(default="./data/memory", description="Agent 记忆文件存放路径")

    model_config = ConfigDict(extra="forbid")


class OrbionConfigFileParser(PydanticBaseSettingsSource):
    """从配置文件加载非密钥配置并校验

    文件不存在时回退到 OrbionConfigSchema 默认值，保持向后兼容。
    """

    _config_data: dict[str, Any]

    @staticmethod
    def _expand_database(data: dict[str, Any]) -> dict[str, Any]:
        """将 database 展开为各特性的具体字段，供 Settings 使用"""
        db_name = data.pop("database", None)
        if db_name is None:
            raise ValueError("配置缺少 database 字段")
        data["event_store"] = db_name
        data["event_projections"] = db_name
        data["project_read"] = db_name
        data["thread_read"] = db_name
        data["user_repo"] = db_name
        return data

    def __init__(self, settings_cls: type[BaseSettings]) -> None:
        super().__init__(settings_cls)
        config_path = os.environ.get("ORBION_CONFIG_PATH", "orbion.json")
        p = Path(config_path)
        if p.exists():
            raw = json.loads(p.read_text())
            validated = OrbionConfigSchema.model_validate(raw)
            self._config_data = self._expand_database(validated.model_dump())
        else:
            defaults = OrbionConfigSchema()
            self._config_data = self._expand_database(defaults.model_dump())

    def get_field_value(self, field: FieldInfo, field_name: str) -> tuple[Any, str, bool]:
        if field_name in self._config_data:
            return self._config_data[field_name], field_name, True
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        return self._config_data


class Settings(BaseSettings):
    """合并配置：orbion.json 基础值 + ORBION_* 环境变量覆盖"""

    # 密钥字段：只从环境变量读取，不出现在 orbion.json 中
    jwt_secret: str = "orbion-dev-secret"
    anthropic_api_key: str = ""

    # 非密钥字段：orbion.json 基础值，环境变量可覆盖
    event_store: str = "postgres"
    event_projections: str = "postgres"
    project_read: str = "postgres"
    thread_read: str = "postgres"
    user_repo: str = "postgres"
    postgres: PostgresSettings = PostgresSettings()
    repo_path: str = "./repo"
    memory_base_path: str = "./data/memory"

    model_config = SettingsConfigDict(env_prefix="ORBION_", env_nested_delimiter="__")

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            OrbionConfigFileParser(settings_cls),
            dotenv_settings,
            file_secret_settings,
        )


def get_settings() -> Settings:
    """模块级便利函数，返回 Settings 实例"""
    return Settings()
