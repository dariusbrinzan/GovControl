import uuid
from datetime import UTC, datetime, timedelta

import jwt

from gateway_app.config import Settings
from gateway_app.models import SessionRecord


def issue_identity_assertion(record: SessionRecord, settings: Settings) -> str:
    """Issue a short-lived assertion; upstream still reloads current RBAC from Platform."""
    if settings.gateway_assertion_secret is None:
        raise RuntimeError("Gateway assertion signing is not configured.")
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "iss": settings.gateway_assertion_issuer,
            "aud": settings.gateway_assertion_audience,
            "sub": record.user.id,
            "tenant_id": record.user.tenant_id,
            "sid": record.id,
            "iat": now,
            "nbf": now,
            "exp": now + timedelta(seconds=settings.gateway_assertion_ttl_seconds),
            "jti": str(uuid.uuid4()),
        },
        settings.gateway_assertion_secret.get_secret_value(),
        algorithm="HS256",
    )
