from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def find_project_root() -> Path:
    """Find the checkout root without assuming the host and image have equal path depth."""
    for parent in Path(__file__).resolve().parents:
        if (parent / ".env").is_file():
            return parent
    return Path.cwd().resolve()


PROJECT_ROOT = find_project_root()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    contracts_database_url: str = Field(
        validation_alias=AliasChoices("CONTRACTS_DATABASE_URL", "DATABASE_URL")
    )
    platform_api_url: str = "http://127.0.0.1:8000/api/v1"
    platform_request_timeout_seconds: float = 5.0
    internal_service_token: SecretStr | None = None
    dev_auth_token: SecretStr | None = None
    redis_url: str = "redis://127.0.0.1:6379/0"
    event_stream_name: str = "govcontrol.events"
    outbox_batch_size: int = 100
    outbox_poll_interval_seconds: float = 2.0
    reminder_scan_interval_seconds: float = 60.0
    cors_allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    @property
    def cors_origins(self) -> list[str]:
        return [item.strip() for item in self.cors_allowed_origins.split(",") if item.strip()]

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        if self.app_env != "production":
            return self
        service_token = (
            self.internal_service_token.get_secret_value()
            if self.internal_service_token is not None
            else ""
        )
        if (
            len(service_token) < 32
            or "change-me" in service_token
            or service_token.startswith("replace-with")
        ):
            raise ValueError("a strong INTERNAL_SERVICE_TOKEN is required in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
