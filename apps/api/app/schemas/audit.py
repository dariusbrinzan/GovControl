import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class AuditEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    actor_user_id: uuid.UUID | None
    action: str
    entity_type: str
    entity_id: uuid.UUID
    old_value: dict[str, Any] | None
    new_value: dict[str, Any] | None
    request_id: uuid.UUID | None
    created_at: datetime


class AuditEventPage(BaseModel):
    items: list[AuditEventResponse]
    limit: int
    offset: int
