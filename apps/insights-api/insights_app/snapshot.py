import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SnapshotModule = Literal["legal", "contracts", "documents", "notifications", "platform"]


class SnapshotRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: uuid.UUID
    module: SnapshotModule
    resource_type: str = Field(pattern=r"^[a-z][a-z0-9_]{1,79}$")
    source_id: uuid.UUID
    identifier: str | None = Field(None, max_length=255)
    display_label: str | None = Field(None, max_length=500)
    status: str | None = Field(None, max_length=80)
    department_id: uuid.UUID | None = None
    responsible_user_id: uuid.UUID | None = None
    occurred_at: datetime | None = None
    due_at: datetime | None = None
    amount: Decimal | None = None
    currency: str | None = Field(None, pattern=r"^[A-Z]{3}$")
    source_url: str = Field(pattern=r"^/[a-z0-9/_-]+$")
    attributes: dict[str, str | int | float | bool | None] = Field(
        default_factory=dict, max_length=20
    )
    source_version: int = Field(ge=1)
    source_event_at: datetime
    deleted: bool = False

    @model_validator(mode="after")
    def validate_controlled_source_url(self) -> "SnapshotRecord":
        allowed_prefixes = {
            "legal": "/legal/",
            "contracts": "/contracts/",
            "documents": "/legal/documents/",
            "notifications": "/legal/notifications",
            "platform": "/platform/",
        }
        if not self.source_url.startswith(allowed_prefixes[self.module]):
            raise ValueError("source_url is not controlled by the record module")
        return self


class ProjectionSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    source: Literal["platform", "contracts", "documents", "notifications"]
    exported_at: datetime
    count: int = Field(ge=0)
    records: list[SnapshotRecord]

    @model_validator(mode="after")
    def validate_count_and_source(self) -> "ProjectionSnapshot":
        if self.count != len(self.records):
            raise ValueError("snapshot count does not match records")
        expected_modules = {
            "platform": {"platform", "legal"},
            "contracts": {"contracts"},
            "documents": {"documents"},
            "notifications": {"notifications"},
        }[self.source]
        if any(record.module not in expected_modules for record in self.records):
            raise ValueError("snapshot contains a record owned by another source")
        return self


def snapshot_document(
    source: str, exported_at: datetime, records: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "source": source,
        "exported_at": exported_at.isoformat(),
        "count": len(records),
        "records": records,
    }
