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


PROJECT_ROOT = find_project_root()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    documents_database_url: str = Field(
        validation_alias=AliasChoices("DOCUMENTS_DATABASE_URL", "DATABASE_URL")
    )
    platform_api_url: str = "http://127.0.0.1:8000/api/v1"
    contracts_api_url: str = "http://127.0.0.1:8010/api/v1"
    dependency_timeout_seconds: float = Field(5.0, gt=0, le=60)
    internal_service_token: SecretStr | None = None
    gateway_assertion_secret: SecretStr | None = None
    gateway_assertion_issuer: str = "govcontrol-gateway"
    gateway_assertion_audience: str = "govcontrol-services"
    redis_url: str = "redis://127.0.0.1:6379/0"
    event_stream_name: str = "govcontrol.events"
    outbox_batch_size: int = Field(100, ge=1, le=1000)
    worker_poll_interval_seconds: float = Field(2.0, gt=0, le=60)
    s3_endpoint_url: str = "http://127.0.0.1:9000"
    s3_access_key: SecretStr = SecretStr("govcontrol")
    s3_secret_key: SecretStr = SecretStr("govcontrol-local-storage-change-me")
    s3_bucket: str = "govcontrol-documents"
    s3_region: str = "us-east-1"
    max_upload_size_bytes: int = Field(25 * 1024 * 1024, ge=1, le=1024 * 1024 * 1024)
    upload_chunk_size_bytes: int = Field(1024 * 1024, ge=64 * 1024, le=8 * 1024 * 1024)
    allowed_content_types: str = (
        "application/pdf,text/plain,text/csv,application/vnd.openxmlformats-officedocument."
        "wordprocessingml.document,application/vnd.openxmlformats-officedocument."
        "spreadsheetml.sheet,image/png,image/jpeg"
    )
    allowed_extensions: str = ".pdf,.txt,.csv,.docx,.xlsx,.png,.jpg,.jpeg"
    malware_scanner_mode: Literal["local_clean", "clamav"] = "local_clean"
    clamav_host: str | None = None
    clamav_port: int = Field(3310, ge=1, le=65535)

    @property
    def content_type_allowlist(self) -> frozenset[str]:
        return frozenset(item.strip().lower() for item in self.allowed_content_types.split(","))

    @property
    def extension_allowlist(self) -> frozenset[str]:
        return frozenset(item.strip().lower() for item in self.allowed_extensions.split(","))

    @model_validator(mode="after")
    def validate_security(self) -> "Settings":
        if self.app_env != "production":
            return self
        for name, value in (
            ("INTERNAL_SERVICE_TOKEN", self.internal_service_token),
            ("GATEWAY_ASSERTION_SECRET", self.gateway_assertion_secret),
            ("S3_SECRET_KEY", self.s3_secret_key),
        ):
            secret = value.get_secret_value() if value is not None else ""
            if len(secret) < 32 or "change-me" in secret or secret.startswith("replace-with"):
                raise ValueError(f"a strong {name} is required in production")
        if self.malware_scanner_mode != "clamav" or not self.clamav_host:
            raise ValueError("a configured ClamAV scanner is required in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
