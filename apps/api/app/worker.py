import asyncio
import json
import logging
import signal
from datetime import UTC, date, datetime

from redis.asyncio import Redis
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import async_session_factory
from app.models.outbox import IntegrationOutboxEvent
from app.models.tenant import Tenant
from app.models.user import User
from app.services.notifications import NotificationService

logger = logging.getLogger("govlegal.worker")


async def publish_batch(redis: Redis, batch_size: int, stream: str) -> int:
    async with async_session_factory() as session, session.begin():
        events = list(
            await session.scalars(
                select(IntegrationOutboxEvent)
                .where(IntegrationOutboxEvent.published_at.is_(None))
                .order_by(IntegrationOutboxEvent.created_at, IntegrationOutboxEvent.id)
                .with_for_update(skip_locked=True)
                .limit(batch_size)
            )
        )
        for event in events:
            envelope = {
                "id": str(event.id),
                "type": event.event_type,
                "tenant_id": str(event.tenant_id),
                "aggregate_type": event.aggregate_type,
                "aggregate_id": str(event.aggregate_id),
                "occurred_at": event.created_at.isoformat(),
                "payload": event.payload,
            }
            await redis.xadd(stream, {"event": json.dumps(envelope, separators=(",", ":"))})
            event.published_at = datetime.now(UTC)
        return len(events)


async def dispatch_deadline_reminders() -> int:
    created = 0
    async with async_session_factory() as session:
        tenant_ids = list(
            await session.scalars(select(Tenant.id).where(Tenant.is_active.is_(True)))
        )
    for tenant_id in tenant_ids:
        async with async_session_factory() as session:
            actor_id = await session.scalar(
                select(User.id)
                .where(User.tenant_id == tenant_id, User.is_active.is_(True))
                .order_by(User.created_at)
                .limit(1)
            )
            if actor_id is not None:
                created += await NotificationService(session).dispatch_deadline_reminders(
                    tenant_id, actor_id, date.today()
                )
    return created


async def run_worker() -> None:
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, stopped.set)
    last_reminder_scan = 0.0
    try:
        while not stopped.is_set():
            try:
                current_time = loop.time()
                if current_time - last_reminder_scan >= settings.reminder_scan_interval_seconds:
                    await dispatch_deadline_reminders()
                    last_reminder_scan = current_time
                published = await publish_batch(
                    redis, settings.outbox_batch_size, settings.event_stream_name
                )
            except Exception:
                logger.exception("govlegal_worker_cycle_failed")
                published = 0
            if not published:
                try:
                    await asyncio.wait_for(
                        stopped.wait(), timeout=settings.outbox_poll_interval_seconds
                    )
                except TimeoutError:
                    pass
    finally:
        await redis.aclose()


def main() -> None:
    settings = get_settings()
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
