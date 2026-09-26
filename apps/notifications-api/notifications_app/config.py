from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def find_project_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / ".env").is_file():
            return parent
    return Path.cwd().resolve()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=find_project_root() / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    notifications_database_url: str = Field(
        validation_alias=AliasChoices("NOTIFICATIONS_DATABASE_URL", "DATABASE_URL")
    )
    platform_api_url: str = "http://127.0.0.1:8000/api/v1"
    dependency_timeout_seconds: float = Field(5.0, gt=0, le=60)
    internal_service_token: SecretStr | None = None
    gateway_assertion_secret: SecretStr | None = None
    gateway_assertion_issuer: str = "govcontrol-gateway"
    gateway_assertion_audience: str = "govcontrol-services"

    redis_url: str = "redis://127.0.0.1:6379/0"
    event_stream_name: str = "govcontrol.events"
    dead_letter_stream_name: str = "govcontrol.notifications.dlq"
    consumer_group: str = "govnotifications-v1"
    consumer_name: str = "notifications-worker-1"
    consumer_batch_size: int = Field(50, ge=1, le=500)
    consumer_block_ms: int = Field(2000, ge=100, le=60000)
    pending_idle_ms: int = Field(30000, ge=1000, le=3600000)
    max_delivery_attempts: int = Field(5, ge=1, le=20)
    retry_base_seconds: int = Field(30, ge=1, le=86400)
    worker_poll_interval_seconds: float = Field(2.0, gt=0, le=60)
    scheduler_interval_seconds: float = Field(30.0, gt=0, le=3600)
    outbox_batch_size: int = Field(100, ge=1, le=1000)
    retention_days: int = Field(365, ge=30, le=3650)

    email_enabled: bool = False
    email_adapter: Literal["local", "smtp"] = "local"
    smtp_host: str | None = None
    smtp_port: int = Field(587, ge=1, le=65535)
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_from_address: str | None = None
    smtp_use_tls: bool = True
    webhook_enabled: bool = False

    @model_validator(mode="after")
    def validate_security_and_channels(self) -> "Settings":
        if self.email_enabled and self.app_env == "production":
            if self.email_adapter != "smtp" or not all(
                (self.smtp_host, self.smtp_username, self.smtp_password, self.smtp_from_address)
            ):
                raise ValueError("EMAIL requires complete SMTP configuration in production")
        if self.webhook_enabled:
            raise ValueError("WEBHOOK is reserved but intentionally disabled")
        if self.app_env == "production":
            for name, value in (
                ("INTERNAL_SERVICE_TOKEN", self.internal_service_token),
                ("GATEWAY_ASSERTION_SECRET", self.gateway_assertion_secret),
            ):
                secret = value.get_secret_value() if value is not None else ""
                if len(secret) < 32 or "change-me" in secret or secret.startswith("replace-with"):
                    raise ValueError(f"a strong {name} is required in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
