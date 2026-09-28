import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from insights_app.config import Settings
from insights_app.schemas import UserContext
from insights_app.security import assertion_ids, require_permission


def settings() -> Settings:
    return Settings(
        insights_database_url="postgresql+asyncpg://user:pass@db/test",
        gateway_assertion_secret="a" * 40,
    )


def test_gateway_assertion_is_cryptographically_bound_to_user_and_tenant() -> None:
    config = settings()
    user_id, tenant_id = uuid.uuid4(), uuid.uuid4()
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": str(user_id),
            "tenant_id": str(tenant_id),
            "iss": config.gateway_assertion_issuer,
            "aud": config.gateway_assertion_audience,
            "iat": now,
            "nbf": now,
            "exp": now + timedelta(seconds=60),
        },
        "a" * 40,
        algorithm="HS256",
    )
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    assert assertion_ids(credentials, config) == (user_id, tenant_id)


def test_browser_supplied_unsigned_identity_is_rejected() -> None:
    with pytest.raises(HTTPException) as exc:
        assertion_ids(None, settings())
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_permission_dependency_rejects_missing_insights_scope() -> None:
    context = UserContext(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        email="officer@example.test",
        display_name="Officer",
        roles=["legal_officer"],
        permissions=["legal.manage"],
    )
    dependency = require_permission("insights.read")
    with pytest.raises(HTTPException) as exc:
        await dependency(context)
    assert exc.value.status_code == 403
