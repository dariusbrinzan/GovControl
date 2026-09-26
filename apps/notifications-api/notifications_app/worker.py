import asyncio
import json
import logging
import signal
import time
from datetime import UTC, datetime

from redis.asyncio import Redis
from redis.exceptions import ResponseError
from sqlalchemy import select

from notifications_app.config import Settings, get_settings
from notifications_app.database import session_factory
from notifications_app.events import UnsupportedEventError, notification_from_event
from notifications_app.models import OutboxEvent
from notifications_app.service import NotificationService

logger = logging.getLogger("govnotifications.worker")


async def ensure_group(redis: Redis, settings: Settings) -> None:
    try:
        await redis.xgroup_create(
            settings.event_stream_name, settings.consumer_group, id="0", mkstream=True
        )
    except ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


async def publish_outbox(redis: Redis, settings: Settings) -> int:
    async with session_factory() as session, session.begin():
        rows = list(
            await session.scalars(
                select(OutboxEvent)
                .where(OutboxEvent.published_at.is_(None))
                .order_by(OutboxEvent.created_at, OutboxEvent.id)
                .with_for_update(skip_locked=True)
                .limit(settings.outbox_batch_size)
            )
        )
        for event in rows:
            envelope = {
                "id": str(event.id),
                "type": event.event_type,
                "tenant_id": str(event.tenant_id),
                "aggregate_type": "Notification",
                "aggregate_id": str(event.aggregate_id),
                "occurred_at": event.created_at.isoformat(),
                "payload": event.payload,
            }
            await redis.xadd(
                settings.event_stream_name,
                {"event": json.dumps(envelope, separators=(",", ":"))},
            )
            event.published_at = datetime.now(UTC)
        return len(rows)


async def _dead_letter(
    redis: Redis,
    settings: Settings,
    message_id: str,
    fields: dict[str, str],
    reason: str,
    attempts: int,
) -> None:
    await redis.xadd(
        settings.dead_letter_stream_name,
        {
            "source_stream": settings.event_stream_name,
            "source_message_id": message_id,
            "reason": reason[:200],
            "attempts": str(attempts),
            "event": fields.get("event", "")[:8192],
        },
    )
    await redis.xack(settings.event_stream_name, settings.consumer_group, message_id)


async def process_message(
    redis: Redis,
    settings: Settings,
    message_id: str,
    fields: dict[str, str],
) -> bool:
    retry_key = f"govnotifications:retry:{message_id}"
    retry_after_key = f"{retry_key}:after"
    retry_after = await redis.get(retry_after_key)
    if retry_after is not None and float(retry_after) > time.time():
        return False
    try:
        raw = fields.get("event")
        if raw is None:
            raise ValueError("Missing event field.")
        envelope = json.loads(raw)
        if not isinstance(envelope, dict):
            raise ValueError("Invalid event body.")
        try:
            value = notification_from_event(envelope)
        except UnsupportedEventError as exc:
            if "not subscribed" in str(exc):
                await redis.xack(settings.event_stream_name, settings.consumer_group, message_id)
                return True
            raise
        async with session_factory() as session:
            await NotificationService(session).ingest(value, message_id)
        await redis.xack(settings.event_stream_name, settings.consumer_group, message_id)
        await redis.delete(retry_key)
        await redis.delete(retry_after_key)
        return True
    except Exception as exc:
        attempts = int(await redis.incr(retry_key))
        await redis.expire(retry_key, 7 * 24 * 60 * 60)
        logger.warning(
            "event_processing_failed message_id=%s attempts=%s error_type=%s",
            message_id,
            attempts,
            type(exc).__name__,
        )
        if attempts >= settings.max_delivery_attempts:
            await _dead_letter(
                redis, settings, message_id, fields, type(exc).__name__, attempts
            )
            await redis.delete(retry_key)
            await redis.delete(retry_after_key)
        else:
            delay = settings.retry_base_seconds * 2 ** max(0, attempts - 1)
            await redis.set(retry_after_key, str(time.time() + delay), ex=7 * 24 * 60 * 60)
        return False


async def consume_new(redis: Redis, settings: Settings) -> int:
    batches = await redis.xreadgroup(
        settings.consumer_group,
        settings.consumer_name,
        {settings.event_stream_name: ">"},
        count=settings.consumer_batch_size,
        block=settings.consumer_block_ms,
    )
    processed = 0
    for _, messages in batches:
        for message_id, fields in messages:
            processed += int(await process_message(redis, settings, message_id, fields))
    return processed


async def recover_pending(redis: Redis, settings: Settings) -> int:
    result = await redis.xautoclaim(
        settings.event_stream_name,
        settings.consumer_group,
        settings.consumer_name,
        min_idle_time=settings.pending_idle_ms,
        start_id="0-0",
        count=settings.consumer_batch_size,
    )
    messages = result[1]
    processed = 0
    for message_id, fields in messages:
        processed += int(await process_message(redis, settings, message_id, fields))
    return processed


async def run_worker() -> None:
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, stopped.set)
    try:
        await ensure_group(redis, settings)
        while not stopped.is_set():
            try:
                await recover_pending(redis, settings)
                await publish_outbox(redis, settings)
                await consume_new(redis, settings)
            except Exception:
                logger.exception("notification_worker_cycle_failed")
                try:
                    await asyncio.wait_for(
                        stopped.wait(), timeout=settings.worker_poll_interval_seconds
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
