import asyncio
import logging
import signal
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select

from notifications_app.config import get_settings
from notifications_app.database import session_factory
from notifications_app.models import (
    DeliveryAttempt,
    DeliveryStatus,
    Notification,
    NotificationAuditEvent,
    NotificationSchedule,
)
from notifications_app.schemas import InternalNotificationCreate
from notifications_app.service import NotificationService

logger = logging.getLogger("govnotifications.scheduler")


async def process_due_schedules(batch_size: int = 100) -> int:
    now = datetime.now(UTC)
    async with session_factory() as session:
        rows = list(
            await session.scalars(
                select(NotificationSchedule)
                .where(
                    NotificationSchedule.processed_at.is_(None),
                    NotificationSchedule.scheduled_for <= now,
                )
                .order_by(NotificationSchedule.scheduled_for)
                .with_for_update(skip_locked=True)
                .limit(batch_size)
            )
        )
        count = 0
        for row in rows:
            await NotificationService(session).ingest(
                InternalNotificationCreate(
                    event_id=row.id,
                    event_type="notification.schedule.due.v1",
                    tenant_id=row.tenant_id,
                    recipient_user_id=row.recipient_user_id,
                    resource_type=row.resource_type,
                    resource_id=row.resource_id,
                    template_key=row.template_key,
                    variables={key: str(value) for key, value in row.variables.items()},
                    deduplication_key=row.deduplication_key,
                ),
                stream_message_id=f"schedule:{row.id}",
            )
            row.processed_at = now
            count += 1
        await session.commit()
        return count


async def queue_failed_deliveries() -> int:
    settings = get_settings()
    now = datetime.now(UTC)
    async with session_factory() as session, session.begin():
        rows = list(
            await session.scalars(
                select(DeliveryAttempt)
                .where(
                    DeliveryAttempt.status.in_([DeliveryStatus.PENDING, DeliveryStatus.FAILED]),
                    DeliveryAttempt.next_attempt_at <= now,
                )
                .with_for_update(skip_locked=True)
                .limit(settings.consumer_batch_size)
            )
        )
        for row in rows:
            row.attempt_count += 1
            if row.attempt_count >= settings.max_delivery_attempts:
                row.status = DeliveryStatus.DEAD_LETTER
                row.next_attempt_at = None
                row.last_error_code = "DELIVERY_LIMIT_REACHED"
            else:
                row.status = DeliveryStatus.FAILED
                delay = settings.retry_base_seconds * 2 ** max(0, row.attempt_count - 1)
                row.next_attempt_at = now + timedelta(seconds=delay)
                row.last_error_code = "ADAPTER_UNAVAILABLE"
        return len(rows)


async def cleanup_expired() -> int:
    settings = get_settings()
    cutoff = datetime.now(UTC) - timedelta(days=settings.retention_days)
    async with session_factory() as session, session.begin():
        await session.execute(
            delete(NotificationAuditEvent).where(NotificationAuditEvent.created_at < cutoff)
        )
        result = await session.scalars(
            delete(Notification).where(
                Notification.expires_at.is_not(None), Notification.expires_at < datetime.now(UTC)
            ).returning(Notification.id)
        )
        return len(result.all())


async def run_scheduler() -> None:
    settings = get_settings()
    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, stopped.set)
    while not stopped.is_set():
        try:
            await process_due_schedules(settings.consumer_batch_size)
            await queue_failed_deliveries()
            await cleanup_expired()
        except Exception:
            logger.exception("notification_scheduler_cycle_failed")
        try:
            await asyncio.wait_for(stopped.wait(), timeout=settings.scheduler_interval_seconds)
        except TimeoutError:
            pass


def main() -> None:
    settings = get_settings()
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
    asyncio.run(run_scheduler())


if __name__ == "__main__":
    main()
