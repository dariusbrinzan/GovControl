import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from notifications_app.models import Channel, DeliveryStatus, NotificationStatus, Severity


class UserContext(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    email: str
    display_name: str
    roles: list[str]
    permissions: list[str]


class NotificationItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    category: str
    severity: Severity
    title: str
    body: str
    resource_type: str | None
    resource_id: uuid.UUID | None
    resource_url: str | None
    status: NotificationStatus
    read_at: datetime | None
    archived_at: datetime | None
    created_at: datetime


class NotificationPage(BaseModel):
    items: list[NotificationItem]
    total: int
    limit: int
    offset: int


class UnreadCount(BaseModel):
    count: int


class BulkMutationResult(BaseModel):
    updated: int


class PreferenceInput(BaseModel):
    category: str = Field(min_length=1, max_length=100)
    channel: Channel
    enabled: bool
    quiet_hours_start: str | None = Field(None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    quiet_hours_end: str | None = Field(None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")


class PreferenceResponse(PreferenceInput):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    updated_at: datetime


class TemplateCreate(BaseModel):
    key: str = Field(pattern=r"^[a-z0-9][a-z0-9_.-]{2,149}$")
    title_template: str = Field(min_length=1, max_length=500)
    body_template: str = Field(min_length=1, max_length=4000)
    allowed_variables: list[str] = Field(max_length=30)
    default_category: str = Field(min_length=1, max_length=100)
    default_severity: Severity = Severity.INFO

    @field_validator("allowed_variables")
    @classmethod
    def unique_variables(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("allowed_variables must be unique")
        return value


class TemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    key: str
    version: int
    title_template: str
    body_template: str
    allowed_variables: list[str]
    default_category: str
    default_severity: Severity
    active: bool
    created_at: datetime


class DeliveryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    notification_id: uuid.UUID
    recipient_user_id: uuid.UUID
    channel: Channel
    status: DeliveryStatus
    attempt_count: int
    next_attempt_at: datetime | None
    delivered_at: datetime | None
    last_error_code: str | None


class AuditResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    actor_user_id: uuid.UUID | None
    notification_id: uuid.UUID | None
    action: str
    request_id: uuid.UUID | None
    payload: dict[str, Any] | None
    created_at: datetime


class InternalNotificationCreate(BaseModel):
    event_id: uuid.UUID
    event_type: str = Field(min_length=1, max_length=200)
    tenant_id: uuid.UUID
    recipient_user_id: uuid.UUID
    resource_type: str | None = Field(None, max_length=100)
    resource_id: uuid.UUID | None = None
    resource_url: str | None = Field(None, max_length=500, pattern=r"^/[a-z0-9/_-]+$")
    template_key: str = Field(min_length=1, max_length=150)
    variables: dict[str, str] = Field(default_factory=dict)
    deduplication_key: str = Field(min_length=1, max_length=255)


class RetryResult(BaseModel):
    queued: bool
