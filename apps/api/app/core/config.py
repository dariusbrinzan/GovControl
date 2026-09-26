from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def find_project_root() -> Path:
    """Find the checkout root without assuming the host and image have equal path depth."""
    for parent in Path(__file__).resolve().parents:
        if (parent / ".env").is_file():
            return parent
    return Path.cwd().resolve()


PROJECT_ROOT = find_project_root()


class Settings(BaseSettings):
    """Environment-backed application settings."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["development", "test", "production"] = "development"
    database_url: str
    log_level: str = "INFO"
    dev_auth_enabled: bool = False
    dev_auth_token: SecretStr | None = None
    dev_auth_email: str | None = None
    internal_service_token: SecretStr | None = None
    gateway_assertion_secret: SecretStr | None = None
    gateway_assertion_issuer: str = "govcontrol-gateway"
    gateway_assertion_audience: str = "govcontrol-services"
    oidc_trusted_issuers: str = ""
    federated_email_linking_enabled: bool = False
    document_storage_backend: Literal["local", "s3"] = "local"
    document_storage_path: Path = PROJECT_ROOT / "data" / "documents"
    s3_endpoint_url: str = "http://127.0.0.1:9000"
    s3_access_key: SecretStr = SecretStr("govcontrol")
    s3_secret_key: SecretStr = SecretStr("govcontrol-local-storage-change-me")
    s3_bucket: str = "govcontrol-documents"
    s3_region: str = "us-east-1"
    max_document_size_bytes: int = 10 * 1024 * 1024
    cors_allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    response_compression_minimum_size: int = 1000
    contracts_api_url: str = "http://127.0.0.1:8010/api/v1"
    service_request_timeout_seconds: float = 5.0

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]

    @property
    def trusted_oidc_issuers(self) -> frozenset[str]:
        return frozenset(
            issuer.strip().rstrip("/")
            for issuer in self.oidc_trusted_issuers.split(",")
            if issuer.strip()
        )

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
        assertion_secret = (
            self.gateway_assertion_secret.get_secret_value()
            if self.gateway_assertion_secret is not None
            else ""
        )
        if (
            len(assertion_secret) < 32
            or "change-me" in assertion_secret
            or assertion_secret.startswith("replace-with")
            or assertion_secret.startswith("govcontrol-local-")
        ):
            raise ValueError("a strong GATEWAY_ASSERTION_SECRET is required in production")
        if not self.trusted_oidc_issuers or any(
            not issuer.startswith("https://") for issuer in self.trusted_oidc_issuers
        ):
            raise ValueError("HTTPS OIDC_TRUSTED_ISSUERS are required in production")
        if self.document_storage_backend == "s3":
            storage_secret = self.s3_secret_key.get_secret_value()
            if (
                len(storage_secret) < 32
                or "change-me" in storage_secret
                or storage_secret.startswith("replace-with")
            ):
                raise ValueError("a strong S3_SECRET_KEY is required in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
