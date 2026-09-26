import pytest

from documents_app.config import Settings


def test_production_requires_strong_secrets_and_real_scanner() -> None:
    with pytest.raises(ValueError, match="INTERNAL_SERVICE_TOKEN"):
        Settings(
            app_env="production",
            database_url="postgresql+asyncpg://user:password@localhost/test",
            internal_service_token="",
            gateway_assertion_secret="g" * 40,
            s3_secret_key="s" * 40,
            malware_scanner_mode="clamav",
            clamav_host="scanner",
        )
    with pytest.raises(ValueError, match="ClamAV"):
        Settings(
            app_env="production",
            database_url="postgresql+asyncpg://user:password@localhost/test",
            internal_service_token="i" * 40,
            gateway_assertion_secret="g" * 40,
            s3_secret_key="s" * 40,
            malware_scanner_mode="local_clean",
        )


def test_development_accepts_explicit_local_scanner() -> None:
    settings = Settings(
        app_env="development",
        database_url="postgresql+asyncpg://user:password@localhost/test",
        malware_scanner_mode="local_clean",
    )
    assert settings.malware_scanner_mode == "local_clean"
