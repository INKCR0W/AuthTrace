from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = Field(default="AuthTrace API", alias="AUTHTRACE_APP_NAME")
    env: str = Field(default="development", alias="AUTHTRACE_ENV")
    debug: bool = Field(default=False, alias="AUTHTRACE_DEBUG")
    api_v1_prefix: str = Field(default="/api/v1", alias="AUTHTRACE_API_V1_PREFIX")
    database_url: str = Field(
        default="postgresql+psycopg://authtrace:authtrace@localhost:5432/authtrace",
        alias="AUTHTRACE_DATABASE_URL",
    )
    timezone: str = Field(default="UTC", alias="AUTHTRACE_TIMEZONE")
    management_source_key: str = Field(default="main", alias="AUTHTRACE_MANAGEMENT_SOURCE_KEY")
    management_source_name: str = Field(default="默认管理端", alias="AUTHTRACE_MANAGEMENT_SOURCE_NAME")
    management_source_description: str | None = Field(
        default=None,
        alias="AUTHTRACE_MANAGEMENT_SOURCE_DESCRIPTION",
    )
    management_base_url: str | None = Field(default=None, alias="AUTHTRACE_MANAGEMENT_BASE_URL")
    management_token: str | None = Field(default=None, alias="AUTHTRACE_MANAGEMENT_TOKEN")
    management_timeout_seconds: float = Field(default=30.0, alias="AUTHTRACE_MANAGEMENT_TIMEOUT_SECONDS")
    management_user_agent: str = Field(
        default="AuthTrace/0.1 (+https://local.authtrace)",
        alias="AUTHTRACE_MANAGEMENT_USER_AGENT",
    )
    management_target_type: str | None = Field(default=None, alias="AUTHTRACE_MANAGEMENT_TARGET_TYPE")
    management_provider: str | None = Field(default=None, alias="AUTHTRACE_MANAGEMENT_PROVIDER")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("management_base_url")
    @classmethod
    def normalize_base_url(cls, value: str | None) -> str | None:
        if value is None:
            return None

        normalized = value.strip().rstrip("/")
        return normalized or None

    @field_validator("management_target_type", "management_provider", "management_token")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None

        normalized = value.strip()
        return normalized or None

    @property
    def management_is_configured(self) -> bool:
        return bool(self.management_base_url and self.management_token)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
