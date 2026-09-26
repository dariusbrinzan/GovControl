import uuid
from datetime import UTC, datetime, timedelta
from typing import cast
from unittest.mock import AsyncMock

import jwt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.core.config import Settings
from app.core.observability import request_id_from_header
from app.core.security import AuthenticatedUser, get_current_user, require_internal_service
from app.db.session import AsyncSession


@pytest.mark.asyncio
async def test_development_auth_is_unavailable_when_disabled() -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://user:password@localhost:5432/test",
        dev_auth_enabled=False,
    )

    with pytest.raises(HTTPException) as exception_info:
        await get_current_user(settings, cast(AsyncSession, object()), None)

    assert exception_info.value.status_code == 503


@pytest.mark.asyncio
async def test_development_auth_rejects_a_missing_bearer_token() -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://user:password@localhost:5432/test",
        dev_auth_enabled=True,
        dev_auth_token="local-token",
        dev_auth_email="admin@govcontrol.local",
    )

    with pytest.raises(HTTPException) as exception_info:
        await get_current_user(settings, cast(AsyncSession, object()), None)

    assert exception_info.value.status_code == 401


def test_internal_service_authentication_uses_constant_time_secret_check() -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://user:password@localhost:5432/test",
        internal_service_token="service-secret",
    )

    require_internal_service(settings, "service-secret")

    with pytest.raises(HTTPException) as exception_info:
        require_internal_service(settings, "incorrect-secret")

    assert exception_info.value.status_code == 401


def test_production_requires_internal_service_secret() -> None:
    with pytest.raises(ValueError, match="strong INTERNAL_SERVICE_TOKEN"):
        Settings(
            app_env="production",
            database_url="postgresql+asyncpg://user:password@localhost:5432/test",
        )


def test_production_rejects_placeholder_service_secret() -> None:
    with pytest.raises(ValueError, match="strong INTERNAL_SERVICE_TOKEN"):
        Settings(
            app_env="production",
            database_url="postgresql+asyncpg://user:password@localhost:5432/test",
            internal_service_token="govcontrol-local-internal-token-change-me",
        )


def test_production_requires_gateway_assertion_and_oidc_issuer() -> None:
    with pytest.raises(ValueError, match="GATEWAY_ASSERTION_SECRET"):
        Settings(
            app_env="production",
            database_url="postgresql+asyncpg://user:password@localhost:5432/test",
            internal_service_token="i" * 40,
        )
    with pytest.raises(ValueError, match="OIDC_TRUSTED_ISSUERS"):
        Settings(
            app_env="production",
            database_url="postgresql+asyncpg://user:password@localhost:5432/test",
            internal_service_token="i" * 40,
            gateway_assertion_secret="g" * 40,
        )


@pytest.mark.asyncio
async def test_gateway_assertion_rejects_invalid_signature() -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://user:password@localhost:5432/test",
        gateway_assertion_secret="g" * 40,
    )
    forged = jwt.encode(
        {
            "iss": "govcontrol-gateway",
            "aud": "govcontrol-services",
            "sub": "00000000-0000-0000-0000-000000000001",
            "tenant_id": "00000000-0000-0000-0000-000000000002",
            "iat": 2_000_000_000,
            "nbf": 2_000_000_000,
            "exp": 2_000_000_060,
        },
        "attacker-secret-that-is-long-enough-to-sign",
        algorithm="HS256",
    )
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=forged)
    with pytest.raises(HTTPException) as exception_info:
        await get_current_user(settings, cast(AsyncSession, object()), credentials)
    assert exception_info.value.status_code == 401


@pytest.mark.asyncio
async def test_gateway_assertion_uses_only_signed_user_and_tenant_claims(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    tenant_id = uuid.UUID("00000000-0000-0000-0000-000000000002")
    expected = AuthenticatedUser(
        id=user_id,
        tenant_id=tenant_id,
        department_id=None,
        email="admin@govcontrol.local",
        display_name="Admin",
        roles=frozenset({"platform_admin"}),
        permissions=frozenset({"legal.manage"}),
    )
    loader = AsyncMock(return_value=expected)
    monkeypatch.setattr("app.core.security.load_user_context", loader)
    settings = Settings(
        database_url="postgresql+asyncpg://user:password@localhost:5432/test",
        gateway_assertion_secret="g" * 40,
    )
    now = datetime.now(UTC)
    assertion = jwt.encode(
        {
            "iss": "govcontrol-gateway",
            "aud": "govcontrol-services",
            "sub": str(user_id),
            "tenant_id": str(tenant_id),
            "roles": ["attacker_supplied_role"],
            "iat": now,
            "nbf": now,
            "exp": now + timedelta(seconds=60),
        },
        "g" * 40,
        algorithm="HS256",
    )
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=assertion)
    session = cast(AsyncSession, object())

    result = await get_current_user(settings, session, credentials)

    assert result == expected
    loader.assert_awaited_once_with(session, user_id, tenant_id)


def test_request_id_accepts_uuid_and_replaces_invalid_value() -> None:
    request_id = "ec1f5a2f-e0db-4fcb-b21f-07087f779d39"

    assert str(request_id_from_header(request_id)) == request_id
    assert str(request_id_from_header("not-a-uuid")) != "not-a-uuid"
