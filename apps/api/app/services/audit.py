import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditEvent


class AuditService:
    """Records append-only audit events within the caller's database transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def record_created(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        entity_type: str,
        entity_id: uuid.UUID,
        new_value: dict[str, Any],
    ) -> None:
        self._session.add(
            AuditEvent(
                tenant_id=tenant_id,
                actor_user_id=actor_user_id,
                action="CREATED",
                entity_type=entity_type,
                entity_id=entity_id,
                new_value=new_value,
            )
        )
