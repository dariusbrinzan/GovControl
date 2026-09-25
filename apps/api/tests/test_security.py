from typing import cast

import pytest
from fastapi import HTTPException

from app.core.config import Settings
from app.core.observability import request_id_from_header
from app.core.security import get_current_user, require_internal_service
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
    with pytest.raises(ValueError, match="INTERNAL_SERVICE_TOKEN"):
        Settings(
            app_env="production",
            database_url="postgresql+asyncpg://user:password@localhost:5432/test",
        )


def test_request_id_accepts_uuid_and_replaces_invalid_value() -> None:
    request_id = "ec1f5a2f-e0db-4fcb-b21f-07087f779d39"

    assert str(request_id_from_header(request_id)) == request_id
    assert str(request_id_from_header("not-a-uuid")) != "not-a-uuid"
