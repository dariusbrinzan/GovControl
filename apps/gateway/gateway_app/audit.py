import hashlib
import json
from datetime import UTC, datetime
from typing import Protocol

from gateway_app.models import SessionRecord
from gateway_app.observability import current_request_id


class RedisAuditClient(Protocol):
    async def xadd(self, name: str, fields: dict[str, str]) -> object: ...


async def record_auth_event(
    redis_client: RedisAuditClient,
    action: str,
    *,
    outcome: str,
    session: SessionRecord | None = None,
    detail: str | None = None,
) -> None:
    fields = {
        "occurred_at": datetime.now(UTC).isoformat(),
        "action": action,
        "outcome": outcome,
        "request_id": str(current_request_id() or ""),
        "session_hash": hashlib.sha256(session.id.encode()).hexdigest() if session else "",
        "user_id": session.user.id if session else "",
        "tenant_id": session.user.tenant_id if session else "",
        "auth_method": session.auth_method if session else "",
        "detail": detail or "",
    }
    await redis_client.xadd("govcontrol.auth.audit", {"event": json.dumps(fields)})
