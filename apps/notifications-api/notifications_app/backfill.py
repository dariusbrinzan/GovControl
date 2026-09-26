import argparse
import asyncio
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, TypeAdapter
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from notifications_app.database import session_factory
from notifications_app.models import (
    Channel,
    DeliveryAttempt,
    DeliveryStatus,
    Notification,
    NotificationAuditEvent,
    NotificationRecipient,
    NotificationStatus,
    Severity,
)

BACKFILL_NAMESPACE = uuid.UUID("2dfab02f-1578-45d0-a7a0-f112fab39173")


class LegacyNotification(BaseModel):
    source: str = Field(pattern=r"^(platform|contracts)$")
    legacy_id: uuid.UUID
    tenant_id: uuid.UUID
    recipient_user_id: uuid.UUID
    resource_type: str
    resource_id: uuid.UUID
    category: str
    severity: Severity
    title: str
    body: str
    status: NotificationStatus
    read_at: datetime | None
    created_at: datetime


def load_files(paths: list[Path]) -> list[LegacyNotification]:
    adapter = TypeAdapter(list[LegacyNotification])
    items: list[LegacyNotification] = []
    for path in paths:
        items.extend(adapter.validate_json(path.read_text(encoding="utf-8")))
    return items


async def backfill(items: list[LegacyNotification]) -> dict[str, int]:
    imported = 0
    skipped = 0
    verified = 0
    async with session_factory() as session:
        for item in items:
            deduplication_key = f"legacy:{item.source}:{item.legacy_id}"
            existing = await session.scalar(
                select(Notification).where(
                    Notification.tenant_id == item.tenant_id,
                    Notification.deduplication_key == deduplication_key,
                )
            )
            notification_id = uuid.uuid5(
                BACKFILL_NAMESPACE, f"{item.source}:{item.legacy_id}"
            )
            if existing is None:
                await session.execute(
                    insert(Notification)
                    .values(
                        id=notification_id,
                        tenant_id=item.tenant_id,
                        category=item.category,
                        severity=item.severity,
                        title=item.title,
                        body=item.body,
                        resource_type=item.resource_type,
                        resource_id=item.resource_id,
                        template_key=f"legacy.{item.source}",
                        template_version=0,
                        deduplication_key=deduplication_key,
                        created_at=item.created_at,
                    )
                    .on_conflict_do_nothing(constraint="uq_notification_dedup")
                )
                recipient = NotificationRecipient(
                    notification_id=notification_id,
                    tenant_id=item.tenant_id,
                    user_id=item.recipient_user_id,
                    status=item.status,
                    read_at=item.read_at,
                    created_at=item.created_at,
                )
                delivery = DeliveryAttempt(
                    notification_id=notification_id,
                    tenant_id=item.tenant_id,
                    recipient_user_id=item.recipient_user_id,
                    channel=Channel.IN_APP,
                    status=DeliveryStatus.DELIVERED,
                    attempt_count=1,
                    delivered_at=item.created_at,
                    created_at=item.created_at,
                    updated_at=item.created_at,
                )
                audit = NotificationAuditEvent(
                    tenant_id=item.tenant_id,
                    notification_id=notification_id,
                    action="BACKFILLED",
                    payload={"source": item.source, "legacy_id": str(item.legacy_id)},
                    created_at=item.created_at,
                )
                session.add_all([recipient, delivery, audit])
                await session.commit()
                imported += 1
            else:
                notification_id = existing.id
                skipped += 1
            link = await session.scalar(
                select(NotificationRecipient.id).where(
                    NotificationRecipient.notification_id == notification_id,
                    NotificationRecipient.tenant_id == item.tenant_id,
                    NotificationRecipient.user_id == item.recipient_user_id,
                )
            )
            if link is None:
                raise RuntimeError(f"Backfill verification failed for {item.legacy_id}")
            verified += 1
    return {
        "source": len(items),
        "imported": imported,
        "skipped": skipped,
        "verified": verified,
    }


async def run(paths: list[Path]) -> dict[str, int]:
    return await backfill(load_files(paths))


def main() -> None:
    parser = argparse.ArgumentParser(description="Import GovControl legacy notifications.")
    parser.add_argument("--input", type=Path, action="append", required=True)
    args = parser.parse_args()
    result: dict[str, Any] = asyncio.run(run(args.input))
    print(json.dumps(result))


if __name__ == "__main__":
    main()
