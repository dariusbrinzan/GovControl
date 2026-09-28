import re
import uuid
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from insights_app.models import ProcessedEvent, ProjectionCheckpoint, ProjectionResource
from insights_app.schemas import EventEnvelope

ALLOWED_METADATA = frozenset(
    {
        "identifier",
        "display_label",
        "status",
        "department_id",
        "responsible_user_id",
        "occurred_at",
        "due_at",
        "amount",
        "currency",
        "version",
        "deleted",
        "court",
        "category",
        "delivery_status",
        "processing_status",
        "notification_status",
        "resource_type",
        "source_id",
        "source_url",
    }
)
MODULE_PREFIXES = {
    "legal": "legal",
    "case": "legal",
    "obligation": "legal",
    "enforcement": "legal",
    "penalty": "legal",
    "contracts": "contracts",
    "contract": "contracts",
    "document": "documents",
    "notification": "notifications",
    "platform": "platform",
    "identity": "platform",
    "security": "platform",
}
RESOURCE_PATHS = {
    "case": "/legal/cases/{id}",
    "obligation": "/legal/obligations/{id}",
    "enforcement": "/legal/enforcements/{id}",
    "penalty": "/legal/penalties/{id}",
    "contract": "/contracts/{id}",
    "document": "/legal/documents/{id}",
    "notification": "/legal/notifications",
    "user": "/platform/users/{id}",
    "department": "/platform/departments/{id}",
}
RESOURCE_TYPES = {
    "legalcase": "case",
    "courtdecision": "decision",
    "legalobligation": "obligation",
    "enforcementproceeding": "enforcement",
    "penaltyrule": "penalty",
    "contract": "contract",
    "contractmilestone": "milestone",
    "contractobligation": "contract_obligation",
    "contractpayment": "payment",
    "document": "document",
    "notification": "notification",
    "deliveryattempt": "notification_delivery",
    "user": "user",
    "department": "department",
}
CONTROLLED_SOURCE_URL = re.compile(
    r"^/(?:legal/(?:cases|decisions|obligations|enforcements|penalties|documents)/"
    r"[0-9a-fA-F-]{36}|contracts/[0-9a-fA-F-]{36}|legal/notifications|"
    r"platform/(?:users|departments)/[0-9a-fA-F-]{36})$"
)


def _module(event: EventEnvelope) -> str | None:
    prefix = event.type.split(".", 1)[0].lower()
    aggregate = event.aggregate_type.lower()
    return MODULE_PREFIXES.get(prefix) or MODULE_PREFIXES.get(aggregate)


def _uuid(value: Any) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value)) if value else None
    except (ValueError, TypeError, AttributeError):
        return None


def _datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str):
        try:
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    return result if result.tzinfo else result.replace(tzinfo=UTC)


def _amount(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def controlled_projection(event: EventEnvelope) -> dict[str, Any] | None:
    module = _module(event)
    if module is None:
        return None
    metadata = {key: value for key, value in event.payload.items() if key in ALLOWED_METADATA}
    raw_resource_type = event.aggregate_type.lower().replace("_", "").removesuffix("s")
    resource_type = str(metadata.get("resource_type") or "").lower() or RESOURCE_TYPES.get(
        raw_resource_type, raw_resource_type
    )
    source_id = _uuid(metadata.get("source_id")) or event.aggregate_id
    requested_source_url = str(metadata.get("source_url") or "")
    source_url = (
        requested_source_url
        if CONTROLLED_SOURCE_URL.fullmatch(requested_source_url)
        else RESOURCE_PATHS.get(resource_type, f"/{module}").format(id=source_id)
    )
    identifier = metadata.get("identifier") or event.payload.get("contract_number")
    status = (
        metadata.get("status")
        or event.payload.get("new_status")
        or metadata.get("processing_status")
        or metadata.get("delivery_status")
        or metadata.get("notification_status")
    )
    currency = metadata.get("currency")
    if currency is not None:
        currency = str(currency).upper()
        if len(currency) != 3 or not currency.isalpha():
            currency = None
    version_value = metadata.get("version", 1)
    try:
        version = max(1, int(version_value))
    except (TypeError, ValueError):
        version = 1
    reserved = {
        "identifier",
        "display_label",
        "status",
        "department_id",
        "responsible_user_id",
        "occurred_at",
        "due_at",
        "amount",
        "currency",
        "version",
        "deleted",
        "resource_type",
        "source_id",
        "source_url",
    }
    result: dict[str, Any] = {
        "module": module,
        "resource_type": resource_type,
        "occurred_at": _datetime(metadata.get("occurred_at")) or event.occurred_at,
        "source_url": source_url,
        "source_version": version,
        "source_event_at": event.occurred_at,
    }
    optional = {
        "identifier": str(identifier)[:255] if identifier else None,
        "display_label": str(metadata["display_label"])[:500]
        if metadata.get("display_label")
        else None,
        "status": str(status)[:80] if status else None,
        "department_id": _uuid(metadata.get("department_id")),
        "responsible_user_id": _uuid(metadata.get("responsible_user_id")),
        "due_at": _datetime(metadata.get("due_at")),
        "amount": _amount(metadata.get("amount")),
        "currency": currency,
    }
    presence = {
        "identifier": identifier is not None,
        "display_label": "display_label" in metadata,
        "status": status is not None,
        "department_id": "department_id" in metadata,
        "responsible_user_id": "responsible_user_id" in metadata,
        "due_at": "due_at" in metadata,
        "amount": "amount" in metadata,
        "currency": "currency" in metadata,
    }
    result.update({key: value for key, value in optional.items() if presence[key]})
    attributes = {key: value for key, value in metadata.items() if key not in reserved}
    if attributes:
        result["attributes"] = attributes
    if "deleted" in metadata or event.type.endswith(".deleted.v1"):
        result["deleted"] = bool(metadata.get("deleted", False)) or event.type.endswith(
            ".deleted.v1"
        )
    result["source_id"] = source_id
    return result


async def apply_event(
    session: AsyncSession, event: EventEnvelope, stream_id: str, consumer_group: str
) -> bool:
    if await session.get(ProcessedEvent, event.id) is not None:
        return False
    values = controlled_projection(event)
    if values is not None:
        existing = await session.scalar(
            select(ProjectionResource).where(
                ProjectionResource.tenant_id == event.tenant_id,
                ProjectionResource.module == values["module"],
                ProjectionResource.resource_type == values["resource_type"],
                ProjectionResource.source_id == values["source_id"],
            )
        )
        should_apply = existing is None or (
            values["source_version"] > existing.source_version
            or (
                values["source_version"] == existing.source_version
                and values["source_event_at"] >= existing.source_event_at
            )
        )
        if should_apply:
            if existing is None:
                existing = ProjectionResource(
                    tenant_id=event.tenant_id,
                    source_id=values.pop("source_id"),
                    **values,
                )
                session.add(existing)
            else:
                values.pop("source_id", None)
                for key, value in values.items():
                    setattr(existing, key, value)
    session.add(
        ProcessedEvent(
            event_id=event.id,
            tenant_id=event.tenant_id,
            event_type=event.type,
            stream_id=stream_id,
        )
    )
    checkpoint = await session.get(ProjectionCheckpoint, consumer_group)
    if checkpoint is None:
        processed_at = datetime.now(UTC)
        checkpoint = ProjectionCheckpoint(
            consumer=consumer_group,
            last_stream_id=stream_id,
            last_event_at=event.occurred_at,
            last_processed_at=processed_at,
            last_heartbeat_at=processed_at,
            processed_count=1,
            failed_count=0,
            projection_version=1 if values is not None else 0,
        )
        session.add(checkpoint)
    else:
        checkpoint.last_stream_id = stream_id
        checkpoint.last_event_at = event.occurred_at
        checkpoint.last_processed_at = datetime.now(UTC)
        checkpoint.last_heartbeat_at = checkpoint.last_processed_at
        checkpoint.processed_count += 1
        if values is not None:
            checkpoint.projection_version += 1
    await session.commit()
    return True
