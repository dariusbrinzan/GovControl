import asyncio
import logging
import signal
from datetime import UTC, datetime, timedelta

import httpx
from redis.asyncio import Redis
from sqlalchemy import delete, select

from notifications_app.config import get_settings
from notifications_app.database import session_factory
from notifications_app.delivery import configured_adapters
from notifications_app.models import (
    Channel,
    DeliveryAttempt,
    DeliveryStatus,
    Notification,
    NotificationAuditEvent,
    NotificationSchedule,
    OutboxEvent,
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


async def recipient_address(
    client: httpx.AsyncClient, tenant_id: object, user_id: object
) -> str:
    settings = get_settings()
    if settings.internal_service_token is None:
        raise RuntimeError("IDENTITY_NOT_CONFIGURED")
    response = await client.get(
        f"{settings.platform_api_url.rstrip('/')}/internal/notifications/recipients/"
        f"{tenant_id}/{user_id}",
        headers={"X-Service-Token": settings.internal_service_token.get_secret_value()},
    )
    if response.status_code != 200:
        raise RuntimeError("RECIPIENT_UNAVAILABLE")
    value = response.json().get("email")
    if not isinstance(value, str) or not value:
        raise RuntimeError("RECIPIENT_UNAVAILABLE")
    return value


async def process_deliveries(client: httpx.AsyncClient, redis: Redis) -> int:
    settings = get_settings()
    adapters = configured_adapters(settings)
    now = datetime.now(UTC)
    async with session_factory() as session:
        rows = (
            await session.execute(
                select(DeliveryAttempt, Notification)
                .join(Notification, Notification.id == DeliveryAttempt.notification_id)
                .where(
                    DeliveryAttempt.status.in_([DeliveryStatus.PENDING, DeliveryStatus.FAILED]),
                    DeliveryAttempt.next_attempt_at <= now,
                )
                .with_for_update(skip_locked=True)
                .limit(settings.consumer_batch_size)
            )
        ).all()
        for delivery, notification in rows:
            delivery.attempt_count += 1
            channel = Channel(str(delivery.channel))
            try:
                adapter = adapters.get(channel)
                if adapter is None:
                    raise RuntimeError("ADAPTER_UNAVAILABLE")
                address = None
                if channel == Channel.EMAIL and settings.email_adapter == "smtp":
                    address = await recipient_address(
                        client, delivery.tenant_id, delivery.recipient_user_id
                    )
                await adapter.deliver(notification, address)
                delivery.status = DeliveryStatus.DELIVERED
                delivery.delivered_at = now
                delivery.next_attempt_at = None
                delivery.last_error_code = None
                session.add_all(
                    [
                        NotificationAuditEvent(
                            tenant_id=delivery.tenant_id,
                            notification_id=notification.id,
                            action="DELIVERY_SUCCEEDED",
                            payload={"channel": channel.value},
                        ),
                        OutboxEvent(
                            tenant_id=delivery.tenant_id,
                            event_type="notification.delivery_succeeded.v1",
                            aggregate_id=notification.id,
                            payload={
                                "notification_id": str(notification.id),
                                "channel": channel.value,
                            },
                        ),
                    ]
                )
            except Exception as exc:
                error_code = type(exc).__name__.upper()
                dead_letter = delivery.attempt_count >= settings.max_delivery_attempts
                delivery.status = (
                    DeliveryStatus.DEAD_LETTER if dead_letter else DeliveryStatus.FAILED
                )
                delivery.last_error_code = error_code[:100]
                delay = settings.retry_base_seconds * 2 ** max(0, delivery.attempt_count - 1)
                delivery.next_attempt_at = None if dead_letter else now + timedelta(seconds=delay)
                session.add_all(
                    [
                        NotificationAuditEvent(
                            tenant_id=delivery.tenant_id,
                            notification_id=notification.id,
                            action="DELIVERY_FAILED",
                            payload={
                                "channel": channel.value,
                                "attempt": delivery.attempt_count,
                                "error_code": error_code,
                            },
                        ),
                        OutboxEvent(
                            tenant_id=delivery.tenant_id,
                            event_type="notification.delivery_failed.v1",
                            aggregate_id=notification.id,
                            payload={
                                "notification_id": str(notification.id),
                                "channel": channel.value,
                                "attempt": delivery.attempt_count,
                                "dead_letter": dead_letter,
                            },
                        ),
                    ]
                )
                if dead_letter:
                    await redis.xadd(
                        settings.dead_letter_stream_name,
                        {
                            "delivery_id": str(delivery.id),
                            "notification_id": str(notification.id),
                            "channel": channel.value,
                            "reason": error_code,
                        },
                    )
        await session.commit()
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
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    client = httpx.AsyncClient(
        timeout=httpx.Timeout(settings.dependency_timeout_seconds, connect=3.0),
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
    )
    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, stopped.set)
    try:
        while not stopped.is_set():
            try:
                await process_due_schedules(settings.consumer_batch_size)
                await process_deliveries(client, redis)
                await cleanup_expired()
            except Exception:
                logger.exception("notification_scheduler_cycle_failed")
            try:
                await asyncio.wait_for(stopped.wait(), timeout=settings.scheduler_interval_seconds)
            except TimeoutError:
                pass
    finally:
        await client.aclose()
        await redis.aclose()


def main() -> None:
    settings = get_settings()
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
    asyncio.run(run_scheduler())


if __name__ == "__main__":
    main()
