import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import jwt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from documents_app.config import Settings
from documents_app.models import ResourceType
from documents_app.resources import validate_resource
from documents_app.schemas import UserContext
from documents_app.security import _assertion_ids, get_current_user, require_permission


def test_gateway_assertion_rejects_invalid_signature() -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://user:password@localhost/test",
        gateway_assertion_secret="g" * 40,
    )
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "iss": "govcontrol-gateway",
            "aud": "govcontrol-services",
            "sub": str(uuid.uuid4()),
            "tenant_id": str(uuid.uuid4()),
            "iat": now,
            "nbf": now,
            "exp": now + timedelta(seconds=60),
        },
        "attacker-secret-that-is-long-enough-value",
        algorithm="HS256",
    )
    with pytest.raises(HTTPException) as exception_info:
        _assertion_ids(HTTPAuthorizationCredentials(scheme="Bearer", credentials=token), settings)
    assert exception_info.value.status_code == 401


@pytest.mark.asyncio
async def test_identity_response_must_match_signed_user_and_tenant() -> None:
    user_id, tenant_id = uuid.uuid4(), uuid.uuid4()
    settings = Settings(
        database_url="postgresql+asyncpg://user:password@localhost/test",
        gateway_assertion_secret="g" * 40,
        internal_service_token="internal-service-token",
    )
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "iss": "govcontrol-gateway",
            "aud": "govcontrol-services",
            "sub": str(user_id),
            "tenant_id": str(tenant_id),
            "iat": now,
            "nbf": now,
            "exp": now + timedelta(seconds=60),
        },
        "g" * 40,
        algorithm="HS256",
    )
    response = httpx.Response(
        200,
        json={
            "id": str(user_id),
            "tenant_id": str(uuid.uuid4()),
            "department_id": None,
            "email": "user@example.test",
            "display_name": "User",
            "roles": ["attacker-role"],
            "permissions": ["documents.read"],
        },
    )
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(http_client=AsyncMock())))
    request.app.state.http_client.get.return_value = response
    with pytest.raises(HTTPException) as exception_info:
        await get_current_user(
            request,
            HTTPAuthorizationCredentials(scheme="Bearer", credentials=token),
            settings,
        )
    assert exception_info.value.status_code == 401


@pytest.mark.asyncio
async def test_rbac_rejects_missing_document_permission() -> None:
    dependency = require_permission("documents.delete")
    user = UserContext(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        department_id=None,
        email="officer@example.test",
        display_name="Officer",
        roles=["legal_officer"],
        permissions=["documents.read"],
    )
    with pytest.raises(HTTPException) as exception_info:
        await dependency(user)
    assert exception_info.value.status_code == 403


@pytest.mark.asyncio
async def test_resource_validation_maps_cross_tenant_not_found() -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://user:password@localhost/test",
        internal_service_token="internal-service-token",
    )
    client = AsyncMock()
    client.get.return_value = httpx.Response(404)
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(http_client=client)))
    with pytest.raises(HTTPException) as exception_info:
        await validate_resource(
            request,
            settings,
            "Bearer assertion",
            uuid.uuid4(),
            ResourceType.LEGAL_CASE,
            uuid.uuid4(),
        )
    assert exception_info.value.status_code == 404
    called_url = client.get.await_args.args[0]
    assert "/internal/resources/LegalCase/" in called_url


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "resource_type", [ResourceType.LEGAL_CASE, ResourceType.CONTRACT]
)
async def test_resource_validation_maps_authority_outage_to_503(
    resource_type: ResourceType,
) -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://user:password@localhost/test",
        internal_service_token="internal-service-token",
    )
    client = AsyncMock()
    client.get.side_effect = httpx.ConnectError("authority unavailable")
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(http_client=client)))

    with pytest.raises(HTTPException) as exception_info:
        await validate_resource(
            request,
            settings,
            "Bearer assertion",
            uuid.uuid4(),
            resource_type,
            uuid.uuid4(),
        )

    assert exception_info.value.status_code == 503
