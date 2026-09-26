import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import jwt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from notifications_app.config import Settings
from notifications_app.schemas import UserContext
from notifications_app.security import _assertion_ids, get_current_user, require_permission

DATABASE_URL = "postgresql+asyncpg://user:password@localhost/database"


def assertion(user_id: uuid.UUID, tenant_id: uuid.UUID, secret: str) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "iss": "govcontrol-gateway",
            "aud": "govcontrol-services",
            "sub": str(user_id),
            "tenant_id": str(tenant_id),
            "iat": now,
            "nbf": now,
            "exp": now + timedelta(seconds=60),
        },
        secret,
        algorithm="HS256",
    )


def test_gateway_assertion_rejects_invalid_signature() -> None:
    settings = Settings(
        notifications_database_url=DATABASE_URL,
        gateway_assertion_secret="g" * 40,
    )
    token = assertion(uuid.uuid4(), uuid.uuid4(), "a" * 40)
    with pytest.raises(HTTPException) as info:
        _assertion_ids(HTTPAuthorizationCredentials(scheme="Bearer", credentials=token), settings)
    assert info.value.status_code == 401


@pytest.mark.asyncio
async def test_identity_authority_must_match_asserted_tenant() -> None:
    user_id, tenant_id = uuid.uuid4(), uuid.uuid4()
    secret = "g" * 40
    settings = Settings(
        notifications_database_url=DATABASE_URL,
        gateway_assertion_secret=secret,
        internal_service_token="internal-service-token",
    )
    token = assertion(user_id, tenant_id, secret)
    client = AsyncMock()
    client.get.return_value = httpx.Response(
        200,
        json={
            "id": str(user_id),
            "tenant_id": str(uuid.uuid4()),
            "email": "user@example.test",
            "display_name": "User",
            "roles": ["officer"],
            "permissions": ["notifications.read"],
        },
    )
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(http_client=client)))
    with pytest.raises(HTTPException) as info:
        await get_current_user(
            request,
            HTTPAuthorizationCredentials(scheme="Bearer", credentials=token),
            settings,
        )
    assert info.value.status_code == 401


@pytest.mark.asyncio
async def test_rbac_rejects_missing_permission() -> None:
    dependency = require_permission("notifications.admin")
    user = UserContext(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        email="officer@example.test",
        display_name="Officer",
        roles=["legal_officer"],
        permissions=["notifications.read"],
    )
    with pytest.raises(HTTPException) as info:
        await dependency(user)
    assert info.value.status_code == 403


@pytest.mark.asyncio
async def test_platform_outage_maps_to_service_unavailable() -> None:
    user_id, tenant_id = uuid.uuid4(), uuid.uuid4()
    secret = "g" * 40
    settings = Settings(
        notifications_database_url=DATABASE_URL,
        gateway_assertion_secret=secret,
        internal_service_token="internal-service-token",
    )
    client = AsyncMock()
    client.get.side_effect = httpx.ConnectError("unavailable")
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(http_client=client)))
    with pytest.raises(HTTPException) as info:
        await get_current_user(
            request,
            HTTPAuthorizationCredentials(
                scheme="Bearer", credentials=assertion(user_id, tenant_id, secret)
            ),
            settings,
        )
    assert info.value.status_code == 503
