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
    insights_database_url: str = Field(
        validation_alias=AliasChoices("INSIGHTS_DATABASE_URL", "DATABASE_URL")
    )
    platform_api_url: str = "http://127.0.0.1:8000/api/v1"
    contracts_api_url: str = "http://127.0.0.1:8010/api/v1"
    documents_api_url: str = "http://127.0.0.1:8020/api/v1"
    notifications_api_url: str = "http://127.0.0.1:8030/api/v1"
    internal_service_token: SecretStr | None = None
    gateway_assertion_secret: SecretStr | None = None
    gateway_assertion_issuer: str = "govcontrol-gateway"
    gateway_assertion_audience: str = "govcontrol-services"
    dependency_timeout_seconds: float = Field(5.0, gt=0, le=60)

    redis_url: str = "redis://127.0.0.1:6379/0"
    event_stream_name: str = "govcontrol.events"
    dead_letter_stream_name: str = "govcontrol.insights.dlq"
    consumer_group: str = "govinsights-v1"
    consumer_name: str = "insights-worker-1"
    consumer_batch_size: int = Field(100, ge=1, le=1000)
    consumer_block_ms: int = Field(2000, ge=100, le=60000)
    pending_idle_ms: int = Field(30000, ge=1000, le=3600000)
    max_delivery_attempts: int = Field(5, ge=1, le=20)
    retry_base_seconds: float = Field(1.0, gt=0, le=300)
    worker_poll_interval_seconds: float = Field(1.0, gt=0, le=60)
    outbox_batch_size: int = Field(100, ge=1, le=1000)
    projection_stale_seconds: int = Field(300, ge=30, le=86400)
    dashboard_cache_seconds: int = Field(15, ge=1, le=300)

    export_storage_backend: Literal["local", "s3"] = "local"
    export_storage_path: Path = Path("./data/insights-exports")
    export_bucket: str = "govcontrol-insights"
    s3_endpoint_url: str | None = None
    s3_access_key: str | None = None
    s3_secret_key: SecretStr | None = None
    s3_region: str = "us-east-1"
    export_max_rows: int = Field(100000, ge=1, le=1000000)
    export_max_bytes: int = Field(52428800, ge=1024, le=1073741824)
    export_timeout_seconds: float = Field(120.0, gt=0, le=3600)
    export_retention_hours: int = Field(24, ge=1, le=720)

    @model_validator(mode="after")
    def validate_security(self) -> "Settings":
        if self.export_storage_backend == "s3" and not all(
            (self.s3_endpoint_url, self.s3_access_key, self.s3_secret_key)
        ):
            raise ValueError("S3 export storage requires endpoint and credentials")
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
