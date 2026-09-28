import argparse
import asyncio
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select

from notifications_app.database import session_factory
from notifications_app.models import DeliveryAttempt, Notification, NotificationRecipient


def enum_value(value: object) -> str:
    return str(getattr(value, "value", value))


async def records(tenant_id: uuid.UUID | None = None) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    async with session_factory() as session:
        item: Any
        def scoped(model: Any) -> Any:
            statement = select(model)
            if tenant_id is not None:
                statement = statement.where(model.tenant_id == tenant_id)
            return statement.order_by(model.id)

        for item in await session.scalars(scoped(Notification)):
            output.append(
                {
                    "tenant_id": str(item.tenant_id),
                    "module": "notifications",
                    "resource_type": "notification",
                    "source_id": str(item.id),
                    "identifier": f"NTF-{str(item.id)[:8].upper()}",
                    "display_label": item.category,
                    "status": "CREATED",
                    "occurred_at": item.created_at.isoformat(),
                    "due_at": item.expires_at.isoformat() if item.expires_at else None,
                    "source_url": "/legal/notifications",
                    "attributes": {
                        "category": item.category,
                        "severity": enum_value(item.severity),
                    },
                    "source_version": 1,
                    "source_event_at": item.created_at.isoformat(),
                }
            )
        for item in await session.scalars(
            scoped(NotificationRecipient)
        ):
            output.append(
                {
                    "tenant_id": str(item.tenant_id),
                    "module": "notifications",
                    "resource_type": "notification_recipient",
                    "source_id": str(item.id),
                    "identifier": f"NRC-{str(item.id)[:8].upper()}",
                    "display_label": "Stare notificare",
                    "status": enum_value(item.status),
                    "responsible_user_id": str(item.user_id),
                    "occurred_at": item.created_at.isoformat(),
                    "source_url": "/legal/notifications",
                    "attributes": {"notification_id": str(item.notification_id)},
                    "source_version": 1,
                    "source_event_at": (
                        item.read_at or item.archived_at or item.created_at
                    ).isoformat(),
                }
            )
        for item in await session.scalars(scoped(DeliveryAttempt)):
            output.append(
                {
                    "tenant_id": str(item.tenant_id),
                    "module": "notifications",
                    "resource_type": "notification_delivery",
                    "source_id": str(item.id),
                    "identifier": f"NDL-{str(item.id)[:8].upper()}",
                    "display_label": enum_value(item.channel),
                    "status": enum_value(item.status),
                    "responsible_user_id": str(item.recipient_user_id),
                    "occurred_at": item.created_at.isoformat(),
                    "due_at": item.next_attempt_at.isoformat() if item.next_attempt_at else None,
                    "source_url": "/legal/notifications",
                    "attributes": {"attempt_count": item.attempt_count},
                    "source_version": 1,
                    "source_event_at": item.updated_at.isoformat(),
                }
            )
    return output


async def snapshot(tenant_id: uuid.UUID | None = None) -> dict[str, object]:
    values = await records(tenant_id)
    return {
        "schema_version": 1,
        "source": "notifications",
        "exported_at": datetime.now(UTC).isoformat(),
        "count": len(values),
        "records": values,
    }


async def export(path: Path) -> None:
    document = await snapshot()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, separators=(",", ":")), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export controlled GovNotifications metadata")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    asyncio.run(export(args.output))


if __name__ == "__main__":
    main()
