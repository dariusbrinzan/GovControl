import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.models.notification import NotificationStatus


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    notification_type: str
    title: str
    body: str
    due_date: date | None
    status: NotificationStatus
    read_at: datetime | None
    created_at: datetime


class NotificationDispatchResponse(BaseModel):
    created: int
