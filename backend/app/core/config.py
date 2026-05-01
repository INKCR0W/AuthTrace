from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = Field(default="AuthTrace API", alias="AUTHTRACE_APP_NAME")
    env: str = Field(default="development", alias="AUTHTRACE_ENV")
    debug: bool = Field(default=False, alias="AUTHTRACE_DEBUG")
    api_v1_prefix: str = Field(default="/api/v1", alias="AUTHTRACE_API_V1_PREFIX")
    cors_allowed_origins: Annotated[tuple[str, ...], NoDecode] = Field(
        default=("http://localhost:5173", "http://127.0.0.1:5173"),
        alias="AUTHTRACE_CORS_ALLOWED_ORIGINS",
    )
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
    management_probe_concurrency: int = Field(default=4, alias="AUTHTRACE_MANAGEMENT_PROBE_CONCURRENCY")
    scheduler_enabled: bool = Field(default=False, alias="AUTHTRACE_SCHEDULER_ENABLED")
    scheduler_interval_minutes: int = Field(default=15, alias="AUTHTRACE_SCHEDULER_INTERVAL_MINUTES")
    management_user_agent: str = Field(
        default="AuthTrace/0.1 (+https://local.authtrace)",
        alias="AUTHTRACE_MANAGEMENT_USER_AGENT",
    )
    management_target_type: str | None = Field(default=None, alias="AUTHTRACE_MANAGEMENT_TARGET_TYPE")
    management_provider: str | None = Field(default=None, alias="AUTHTRACE_MANAGEMENT_PROVIDER")
    management_weekly_quota_threshold: float = Field(
        default=95.0,
        alias="AUTHTRACE_MANAGEMENT_WEEKLY_QUOTA_THRESHOLD",
    )
    management_short_quota_threshold: float = Field(
        default=95.0,
        alias="AUTHTRACE_MANAGEMENT_SHORT_QUOTA_THRESHOLD",
    )

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

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def parse_cors_allowed_origins(cls, value: object) -> tuple[str, ...]:
        if value is None:
            return ()

        if isinstance(value, str):
            normalized_items = [item.strip().rstrip("/") for item in value.split(",")]
            return tuple(item for item in normalized_items if item)

        if isinstance(value, (list, tuple, set)):
            normalized_items = []
            for item in value:
                if not isinstance(item, str):
                    continue
                normalized = item.strip().rstrip("/")
                if normalized:
                    normalized_items.append(normalized)
            return tuple(normalized_items)

        raise ValueError("cors allowed origins must be a comma-separated string or string list")

    @field_validator("management_target_type", "management_provider", "management_token")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None

        normalized = value.strip()
        return normalized or None

    @field_validator("management_weekly_quota_threshold", "management_short_quota_threshold")
    @classmethod
    def validate_quota_threshold(cls, value: float) -> float:
        if not 0 <= value <= 100:
            raise ValueError("quota threshold must be between 0 and 100")
        return value

    @field_validator("management_probe_concurrency")
    @classmethod
    def validate_probe_concurrency(cls, value: int) -> int:
        if value < 1:
            raise ValueError("management probe concurrency must be at least 1")
        return value

    @field_validator("scheduler_interval_minutes")
    @classmethod
    def validate_scheduler_interval_minutes(cls, value: int) -> int:
        if value < 1:
            raise ValueError("scheduler interval minutes must be at least 1")
        return value

    @property
    def management_is_configured(self) -> bool:
        return bool(self.management_base_url and self.management_token)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
