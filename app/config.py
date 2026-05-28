"""Orbion MVP 配置管理"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    postgres_url: str = "postgresql://orbion:orbion_dev@localhost:5432/orbion"
    jwt_secret: str = "orbion-dev-secret"
    anthropic_api_key: str = ""
    repo_path: str = "./repo"
    memory_base_path: str = "./data/memory"

    model_config = SettingsConfigDict(env_prefix="ORBION_")
