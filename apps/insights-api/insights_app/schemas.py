import re
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

MODULES = frozenset({"legal", "contracts", "documents", "notifications", "platform"})
REPORT_COLUMNS = frozenset(
    {
        "module",
        "resource_type",
        "identifier",
        "display_label",
        "status",
        "department_id",
        "responsible_user_id",
        "occurred_at",
        "due_at",
        "amount",
        "currency",
    }
)
REPORT_RESOURCE_TYPES = frozenset(
    {
        "case",
        "contract",
        "contract_obligation",
        "decision",
        "department",
        "document",
        "enforcement",
        "milestone",
        "notification",
        "notification_delivery",
        "notification_recipient",
        "obligation",
        "payment",
        "penalty",
        "user",
    }
)


class UserContext(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    department_id: uuid.UUID | None = None
    email: str
    display_name: str
    roles: list[str]
    permissions: list[str]


class DashboardFilter(BaseModel):
    date_from: date | None = None
    date_to: date | None = None
    department_id: uuid.UUID | None = None
    responsible_user_id: uuid.UUID | None = None


class CountBucket(BaseModel):
    key: str
    count: int


class MoneyBucket(BaseModel):
    currency: str
    category: str
    amount: Decimal


class MonthBucket(BaseModel):
    month: str
    count: int


class DashboardResponse(BaseModel):
    module: str | None
    total: int
    by_status: list[CountBucket]
    by_type: list[CountBucket]
    workload_by_department: list[CountBucket]
    workload_by_responsible: list[CountBucket]
    by_court: list[CountBucket] = Field(default_factory=list)
    operational_metrics: dict[str, float] = Field(default_factory=dict)
    financial_exposure: list[MoneyBucket]
    monthly_trend: list[MonthBucket]
    period_total: int
    previous_period_total: int
    period_change_percent: float | None
    overdue: int
    due_soon_7: int
    due_soon_30: int
    due_soon_60: int
    due_soon_90: int
    projection_version: int
    last_updated_at: datetime | None
    stale: bool


class SearchItem(BaseModel):
    id: uuid.UUID
    module: str
    resource_type: str
    source_id: uuid.UUID
    identifier: str | None
    display_label: str | None
    status: str | None
    source_url: str
    rank: int
    updated_at: datetime


class SearchPage(BaseModel):
    items: list[SearchItem]
    total: int
    limit: int
    offset: int


class ReportCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(None, max_length=1000)
    resource_type: str = Field(min_length=1, max_length=80)
    filters: dict[str, Any] = Field(default_factory=dict)
    columns: list[str] = Field(min_length=1, max_length=20)
    sort: list[dict[str, str]] = Field(default_factory=list, max_length=3)
    shared_with_roles: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("resource_type")
    @classmethod
    def validate_resource_type(cls, value: str) -> str:
        if value not in REPORT_RESOURCE_TYPES:
            raise ValueError("resource_type must be selected from the allowlist")
        return value

    @field_validator("columns")
    @classmethod
    def validate_columns(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)) or any(column not in REPORT_COLUMNS for column in value):
            raise ValueError("columns must be unique and selected from the allowlist")
        return value

    @field_validator("filters")
    @classmethod
    def validate_filters(cls, value: dict[str, Any]) -> dict[str, Any]:
        allowed = {
            "module",
            "status",
            "department_id",
            "responsible_user_id",
            "date_from",
            "date_to",
        }
        if not set(value).issubset(allowed):
            raise ValueError("filters contain unsupported fields")
        normalized = dict(value)
        if module := normalized.get("module"):
            if not isinstance(module, str) or module not in MODULES:
                raise ValueError("unsupported module filter")
        if status := normalized.get("status"):
            if not isinstance(status, str) or len(status.strip()) > 80:
                raise ValueError("status must be a string of at most 80 characters")
            normalized["status"] = status.strip().upper()
        for field_name in ("department_id", "responsible_user_id"):
            if raw_value := normalized.get(field_name):
                try:
                    normalized[field_name] = str(uuid.UUID(str(raw_value)))
                except (ValueError, TypeError, AttributeError) as exc:
                    raise ValueError(f"{field_name} must be a UUID") from exc
        parsed_dates: dict[str, date] = {}
        for field_name in ("date_from", "date_to"):
            if raw_value := normalized.get(field_name):
                try:
                    parsed = (
                        raw_value
                        if isinstance(raw_value, date)
                        else date.fromisoformat(raw_value)
                    )
                except (ValueError, TypeError) as exc:
                    raise ValueError(f"{field_name} must be an ISO date") from exc
                parsed_dates[field_name] = parsed
                normalized[field_name] = parsed.isoformat()
        if parsed_dates.get("date_from") and parsed_dates.get("date_to"):
            if parsed_dates["date_from"] > parsed_dates["date_to"]:
                raise ValueError("date_from must precede date_to")
        return normalized

    @field_validator("shared_with_roles")
    @classmethod
    def validate_shared_roles(cls, value: list[str]) -> list[str]:
        normalized = [role.strip() for role in value]
        if len(normalized) != len(set(normalized)) or any(
            not re.fullmatch(r"[a-z][a-z0-9_.:-]{1,99}", role) for role in normalized
        ):
            raise ValueError("shared roles must be unique role keys")
        return normalized

    @field_validator("sort")
    @classmethod
    def validate_sort(cls, value: list[dict[str, str]]) -> list[dict[str, str]]:
        for item in value:
            if set(item) != {"column", "direction"}:
                raise ValueError("sort items require column and direction")
            if item["column"] not in REPORT_COLUMNS or item["direction"] not in {"asc", "desc"}:
                raise ValueError("unsupported report sort")
        return value


class ReportResponse(ReportCreate):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    owner_user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class RunRequest(BaseModel):
    export_format: Literal["csv", "xlsx"] | None = None


class RunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    report_id: uuid.UUID
    status: str
    row_count: int | None
    error_code: str | None
    requested_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class ExportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    run_id: uuid.UUID
    format: str
    status: str
    size_bytes: int | None
    expires_at: datetime
    created_at: datetime


class AuditResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    actor_user_id: uuid.UUID | None
    action: str
    entity_type: str
    entity_id: uuid.UUID | None
    request_id: uuid.UUID | None
    payload: dict[str, Any] | None
    created_at: datetime


class ProjectionStatusResponse(BaseModel):
    consumer: str
    last_stream_id: str
    last_event_at: datetime | None
    last_processed_at: datetime | None
    last_heartbeat_at: datetime | None
    processed_count: int
    failed_count: int
    projection_version: int
    stale: bool
    lag: int | None = None
    pending: int | None = None


class DeadLetterResponse(BaseModel):
    id: str
    source_stream_id: str
    error: str
    event_id: uuid.UUID
    event_type: str
    occurred_at: datetime


class EventEnvelope(BaseModel):
    id: uuid.UUID
    type: str = Field(min_length=1, max_length=200)
    tenant_id: uuid.UUID
    aggregate_type: str = Field(min_length=1, max_length=100)
    aggregate_id: uuid.UUID
    occurred_at: datetime
    payload: dict[str, Any]
