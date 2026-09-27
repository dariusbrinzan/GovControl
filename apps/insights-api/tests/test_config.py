import pytest
from pydantic import ValidationError

from insights_app.config import Settings


def test_s3_requires_complete_credentials() -> None:
    with pytest.raises(ValidationError, match="requires endpoint and credentials"):
        Settings(
            insights_database_url="postgresql+asyncpg://user:pass@db/test",
            export_storage_backend="s3",
        )


def test_production_rejects_weak_service_secrets() -> None:
    with pytest.raises(ValidationError, match="strong INTERNAL_SERVICE_TOKEN"):
        Settings(
            app_env="production",
            insights_database_url="postgresql+asyncpg://user:pass@db/test",
            internal_service_token="weak",
            gateway_assertion_secret="also-weak",
        )
