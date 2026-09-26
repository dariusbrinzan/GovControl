import pytest
from pydantic import ValidationError

from notifications_app.config import Settings

DATABASE_URL = "postgresql+asyncpg://user:password@localhost/database"


def test_production_rejects_weak_internal_secrets() -> None:
    with pytest.raises(ValidationError, match="INTERNAL_SERVICE_TOKEN"):
        Settings(
            notifications_database_url=DATABASE_URL,
            app_env="production",
            internal_service_token="weak",
            gateway_assertion_secret="weak",
        )


def test_production_rejects_enabled_email_without_smtp() -> None:
    with pytest.raises(ValidationError, match="SMTP"):
        Settings(
            notifications_database_url=DATABASE_URL,
            app_env="production",
            internal_service_token="i" * 40,
            gateway_assertion_secret="g" * 40,
            email_enabled=True,
        )


def test_webhook_is_disabled_in_every_environment() -> None:
    with pytest.raises(ValidationError, match="WEBHOOK"):
        Settings(notifications_database_url=DATABASE_URL, webhook_enabled=True)


def test_local_email_sink_is_valid_in_development() -> None:
    settings = Settings(
        notifications_database_url=DATABASE_URL,
        email_enabled=True,
        email_adapter="local",
    )
    assert settings.email_enabled is True
