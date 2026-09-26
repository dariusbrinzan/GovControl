from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-only gateway configuration with secure production defaults."""

    model_config = SettingsConfigDict(extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    auth_mode: Literal["local", "oidc"] = "local"

    redis_url: str = "redis://127.0.0.1:6379/1"
    platform_api_url: str = "http://127.0.0.1:8000/api/v1"
    contracts_api_url: str = "http://127.0.0.1:8010/api/v1"
    documents_api_url: str = "http://127.0.0.1:8020/api/v1"
    internal_service_token: SecretStr | None = SecretStr(
        "govcontrol-local-internal-token-change-me"
    )
    gateway_assertion_secret: SecretStr | None = SecretStr(
        "govcontrol-local-gateway-assertion-change-me"
    )
    gateway_assertion_issuer: str = "govcontrol-gateway"
    gateway_assertion_audience: str = "govcontrol-services"
    gateway_assertion_ttl_seconds: int = 60
    dev_auth_token: SecretStr | None = None

    session_signing_secret: SecretStr | None = SecretStr(
        "govcontrol-local-session-signing-change-me"
    )
    session_cookie_name: str = "govcontrol_session"
    session_ttl_seconds: int = 8 * 60 * 60
    session_rotation_seconds: int = 30 * 60
    cookie_secure: bool = False
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    cookie_domain: str | None = None

    portal_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    portal_after_login_url: str = "http://localhost:3000/legal"
    public_base_url: str = "http://127.0.0.1:8080"
    request_timeout_seconds: float = 10.0
    connect_timeout_seconds: float = 2.0
    max_request_body_bytes: int = 12 * 1024 * 1024
    max_document_upload_bytes: int = 26 * 1024 * 1024
    document_request_timeout_seconds: float = 60.0
    rate_limit_requests: int = 240
    rate_limit_window_seconds: int = 60
    document_upload_rate_limit_requests: int = 30

    oidc_issuer: str | None = None
    oidc_client_id: str | None = None
    oidc_client_secret: SecretStr | None = None
    oidc_redirect_uri: str | None = None
    oidc_scopes: str = "openid profile email"
    oidc_preauth_ttl_seconds: int = 5 * 60

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.portal_origins.split(",") if origin.strip()]

    @property
    def redirect_uri(self) -> str:
        return self.oidc_redirect_uri or f"{self.public_base_url.rstrip('/')}/auth/callback"

    @staticmethod
    def _strong(secret: SecretStr | None) -> bool:
        if secret is None:
            return False
        value = secret.get_secret_value()
        return (
            len(value) >= 32
            and "change-me" not in value
            and not value.startswith("replace-with")
            and not value.startswith("govcontrol-local-")
        )

    @model_validator(mode="after")
    def validate_security_configuration(self) -> "Settings":
        if self.session_ttl_seconds < 300:
            raise ValueError("SESSION_TTL_SECONDS must be at least 300")
        if not 60 <= self.session_rotation_seconds <= self.session_ttl_seconds:
            raise ValueError("SESSION_ROTATION_SECONDS must fit inside the session lifetime")
        if self.max_request_body_bytes < 1024:
            raise ValueError("MAX_REQUEST_BODY_BYTES must be at least 1024")
        if self.max_document_upload_bytes < self.max_request_body_bytes:
            raise ValueError("MAX_DOCUMENT_UPLOAD_BYTES must cover the general body limit")
        if self.document_request_timeout_seconds <= 0:
            raise ValueError("DOCUMENT_REQUEST_TIMEOUT_SECONDS must be positive")
        if self.rate_limit_requests < 1 or self.rate_limit_window_seconds < 1:
            raise ValueError("rate limiting values must be positive")
        if self.document_upload_rate_limit_requests < 1:
            raise ValueError("DOCUMENT_UPLOAD_RATE_LIMIT_REQUESTS must be positive")
        if self.cookie_samesite == "none" and not self.cookie_secure:
            raise ValueError("COOKIE_SAMESITE=none requires COOKIE_SECURE")
        if not 15 <= self.gateway_assertion_ttl_seconds <= 300:
            raise ValueError("GATEWAY_ASSERTION_TTL_SECONDS must be between 15 and 300")
        if self.auth_mode == "local" and self.app_env == "production":
            raise ValueError("local authentication is forbidden in production")
        if self.auth_mode == "oidc" and not all((self.oidc_issuer, self.oidc_client_id)):
            raise ValueError("OIDC_ISSUER and OIDC_CLIENT_ID are required in OIDC mode")
        if not any(
            self.portal_after_login_url == origin
            or self.portal_after_login_url.startswith(f"{origin}/")
            for origin in self.allowed_origins
        ):
            raise ValueError("PORTAL_AFTER_LOGIN_URL must use an allowed portal origin")
        if self.app_env == "production":
            if not self.cookie_secure:
                raise ValueError("COOKIE_SECURE must be enabled in production")
            for name, secret in (
                ("INTERNAL_SERVICE_TOKEN", self.internal_service_token),
                ("GATEWAY_ASSERTION_SECRET", self.gateway_assertion_secret),
                ("SESSION_SIGNING_SECRET", self.session_signing_secret),
            ):
                if not self._strong(secret):
                    raise ValueError(f"a strong {name} is required in production")
            if not self.public_base_url.startswith("https://"):
                raise ValueError("PUBLIC_BASE_URL must use HTTPS in production")
            if self.oidc_issuer is None or not self.oidc_issuer.startswith("https://"):
                raise ValueError("OIDC_ISSUER must use HTTPS in production")
            if any(not origin.startswith("https://") for origin in self.allowed_origins):
                raise ValueError("all PORTAL_ORIGINS must use HTTPS in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
