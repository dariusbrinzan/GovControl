import asyncio
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import delete, select

from notifications_app.config import get_settings
from notifications_app.database import session_factory
from notifications_app.models import (
    DeliveryAttempt,
    Notification,
    NotificationAuditEvent,
    NotificationRecipient,
    OutboxEvent,
    ProcessedEvent,
)

FIXTURE_PATH = Path("/tmp/govcontrol-notifications-e2e.json")


async def cleanup(path: Path = FIXTURE_PATH) -> dict[str, int]:
    settings = get_settings()
    if settings.app_env != "development":
        raise RuntimeError("E2E cleanup is allowed only in development.")
    if not path.exists():
        return {"notifications": 0, "events": 0}
    payload = json.loads(path.read_text(encoding="utf-8"))
    started_at = datetime.fromisoformat(str(payload["started_at"]).replace("Z", "+00:00"))
    resource_ids = [uuid.UUID(value) for value in payload.get("resource_ids", [])]
    async with session_factory() as session:
        notification_ids = list(
            await session.scalars(
                select(Notification.id).where(
                    Notification.resource_id.in_(resource_ids),
                    Notification.created_at >= started_at,
                )
            )
        )
        event_ids = set(
            await session.scalars(
                select(Notification.source_event_id).where(
                    Notification.id.in_(notification_ids),
                    Notification.source_event_id.is_not(None),
                )
            )
        )
        if notification_ids:
            await session.execute(
                delete(DeliveryAttempt).where(
                    DeliveryAttempt.notification_id.in_(notification_ids)
                )
            )
            await session.execute(
                delete(NotificationRecipient).where(
                    NotificationRecipient.notification_id.in_(notification_ids)
                )
            )
            await session.execute(
                delete(NotificationAuditEvent).where(
                    NotificationAuditEvent.notification_id.in_(notification_ids)
                )
            )
            await session.execute(
                delete(OutboxEvent).where(OutboxEvent.aggregate_id.in_(notification_ids))
            )
            await session.execute(
                delete(Notification).where(Notification.id.in_(notification_ids))
            )
        if event_ids:
            await session.execute(
                delete(ProcessedEvent).where(ProcessedEvent.event_id.in_(event_ids))
            )
        await session.commit()

    removed_events = 0
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        stream_rows: list[tuple[str, dict[str, Any]]] = await redis.xrange(
            settings.event_stream_name
        )
        stream_ids: list[str] = []
        for stream_id, fields in stream_rows:
            try:
                envelope = json.loads(str(fields.get("event", "{}")))
                if uuid.UUID(str(envelope.get("id"))) in event_ids:
                    stream_ids.append(stream_id)
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
        if stream_ids:
            removed_events = int(await redis.xdel(settings.event_stream_name, *stream_ids))
    finally:
        await redis.aclose()
    path.unlink(missing_ok=True)
    return {"notifications": len(notification_ids), "events": removed_events}


def main() -> None:
    print(json.dumps(asyncio.run(cleanup()), sort_keys=True))


if __name__ == "__main__":
    main()
