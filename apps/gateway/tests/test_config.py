import pytest
from pydantic import ValidationError

from gateway_app.config import Settings


def test_production_rejects_local_authentication() -> None:
    with pytest.raises(ValidationError, match="local authentication is forbidden"):
        Settings(app_env="production", auth_mode="local")


def test_production_rejects_insecure_oidc_configuration() -> None:
    with pytest.raises(ValidationError, match="COOKIE_SECURE"):
        Settings(
            app_env="production",
            auth_mode="oidc",
            oidc_issuer="https://identity.example.test",
            oidc_client_id="govcontrol",
        )


def test_production_accepts_strong_oidc_configuration() -> None:
    settings = Settings(
        app_env="production",
        auth_mode="oidc",
        oidc_issuer="https://identity.example.test",
        oidc_client_id="govcontrol",
        public_base_url="https://govcontrol.example.test",
        portal_origins="https://govcontrol.example.test",
        portal_after_login_url="https://govcontrol.example.test/legal",
        cookie_secure=True,
        internal_service_token="i" * 40,
        gateway_assertion_secret="a" * 40,
        session_signing_secret="s" * 40,
    )
    assert settings.redirect_uri == "https://govcontrol.example.test/auth/callback"
