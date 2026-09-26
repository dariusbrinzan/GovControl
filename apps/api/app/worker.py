import asyncio
import json
import logging
import signal
from datetime import UTC, datetime

from redis.asyncio import Redis
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import async_session_factory
from app.models.outbox import IntegrationOutboxEvent

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


async def run_worker() -> None:
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, stopped.set)
    try:
        while not stopped.is_set():
            try:
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
