import asyncio
import json
import logging
import signal
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError
from redis.asyncio import Redis
from redis.exceptions import ResponseError
from sqlalchemy import select

from insights_app.config import Settings, get_settings
from insights_app.database import session_factory
from insights_app.exports import (
    cleanup_expired_exports,
    next_exports,
    next_report_runs,
    process_export,
    process_report_run,
)
from insights_app.models import OutboxEvent, ProjectionCheckpoint
from insights_app.projections import apply_event
from insights_app.schemas import EventEnvelope
from insights_app.storage import create_storage

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("govinsights.worker")


async def ensure_group(redis: Redis, settings: Settings) -> None:
    try:
        await redis.xgroup_create(
            settings.event_stream_name, settings.consumer_group, id="0", mkstream=True
        )
    except ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


async def publish_outbox(redis: Redis, settings: Settings) -> int:
    published = 0
    async with session_factory() as session:
        events = list(
            (
                await session.scalars(
                    select(OutboxEvent)
                    .where(OutboxEvent.published_at.is_(None))
                    .order_by(OutboxEvent.created_at)
                    .limit(settings.outbox_batch_size)
                    .with_for_update(skip_locked=True)
                )
            ).all()
        )
        for event in events:
            envelope = {
                "id": str(event.id),
                "type": event.event_type,
                "tenant_id": str(event.tenant_id),
                "aggregate_type": "insights",
                "aggregate_id": str(event.aggregate_id),
                "occurred_at": event.created_at.isoformat(),
                "payload": event.payload,
            }
            await redis.xadd(
                settings.event_stream_name, {"event": json.dumps(envelope, separators=(",", ":"))}
            )
            event.published_at = datetime.now(UTC)
            published += 1
        await session.commit()
    return published


async def record_heartbeat(settings: Settings) -> None:
    now = datetime.now(UTC)
    async with session_factory() as session:
        checkpoint = await session.get(ProjectionCheckpoint, settings.consumer_group)
        if checkpoint is None:
            checkpoint = ProjectionCheckpoint(
                consumer=settings.consumer_group,
                last_stream_id="0-0",
                last_heartbeat_at=now,
                processed_count=0,
                failed_count=0,
                projection_version=0,
            )
            session.add(checkpoint)
        else:
            checkpoint.last_heartbeat_at = now
        await session.commit()


async def record_failure(settings: Settings, stream_id: str) -> None:
    now = datetime.now(UTC)
    async with session_factory() as session:
        checkpoint = await session.get(ProjectionCheckpoint, settings.consumer_group)
        if checkpoint is None:
            checkpoint = ProjectionCheckpoint(
                consumer=settings.consumer_group,
                last_stream_id=stream_id,
                last_heartbeat_at=now,
                processed_count=0,
                failed_count=1,
                projection_version=0,
            )
            session.add(checkpoint)
        else:
            checkpoint.failed_count += 1
            checkpoint.last_heartbeat_at = now
        await session.commit()


async def process_message(
    redis: Redis, settings: Settings, stream_id: str, fields: dict[str, str]
) -> bool:
    try:
        envelope = EventEnvelope.model_validate_json(fields["event"])
        async with session_factory() as session:
            await apply_event(session, envelope, stream_id, settings.consumer_group)
        await redis.xack(settings.event_stream_name, settings.consumer_group, stream_id)
        return True
    except (KeyError, ValidationError, ValueError, TypeError) as exc:
        await redis.xadd(
            settings.dead_letter_stream_name,
            {
                "stream_id": stream_id,
                "error": type(exc).__name__,
                "event": fields.get("event", "")[:16000],
            },
        )
        await redis.xack(settings.event_stream_name, settings.consumer_group, stream_id)
        await record_failure(settings, stream_id)
        return False


async def consume_new(redis: Redis, settings: Settings) -> int:
    result = await redis.xreadgroup(
        settings.consumer_group,
        settings.consumer_name,
        {settings.event_stream_name: ">"},
        count=settings.consumer_batch_size,
        block=settings.consumer_block_ms,
    )
    processed = 0
    for _, messages in result:
        for stream_id, fields in messages:
            processed += int(await process_message(redis, settings, stream_id, fields))
    return processed


async def recover_pending(redis: Redis, settings: Settings) -> int:
    claimed: Any = await redis.xautoclaim(
        settings.event_stream_name,
        settings.consumer_group,
        settings.consumer_name,
        min_idle_time=settings.pending_idle_ms,
        start_id="0-0",
        count=settings.consumer_batch_size,
    )
    messages = claimed[1] if len(claimed) > 1 else []
    recovered = 0
    for stream_id, fields in messages:
        pending = await redis.xpending_range(
            settings.event_stream_name, settings.consumer_group, stream_id, stream_id, 1
        )
        attempts = int(pending[0].get("times_delivered", 1)) if pending else 1
        if attempts > settings.max_delivery_attempts:
            await redis.xadd(
                settings.dead_letter_stream_name,
                {
                    "stream_id": stream_id,
                    "error": "max_delivery_attempts",
                    "event": fields.get("event", "")[:16000],
                },
            )
            await redis.xack(settings.event_stream_name, settings.consumer_group, stream_id)
            await record_failure(settings, stream_id)
            continue
        await asyncio.sleep(min(settings.retry_base_seconds * (2 ** max(0, attempts - 1)), 30.0))
        recovered += int(await process_message(redis, settings, stream_id, fields))
    return recovered


async def run() -> None:
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    storage = create_storage(settings)
    await storage.ready()
    await ensure_group(redis, settings)
    await record_heartbeat(settings)
    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stopped.set)
    try:
        while not stopped.is_set():
            try:
                await record_heartbeat(settings)
                await publish_outbox(redis, settings)
                await recover_pending(redis, settings)
                async with session_factory() as session:
                    await cleanup_expired_exports(session, storage, datetime.now(UTC))
                    for run_item in await next_report_runs(session, 10):
                        await process_report_run(session, run_item, settings)
                    for artifact in await next_exports(session, 10):
                        await process_export(session, storage, artifact, settings)
                await consume_new(redis, settings)
            except Exception:
                logger.exception("worker_iteration_failed")
                try:
                    await asyncio.wait_for(
                        stopped.wait(), timeout=settings.worker_poll_interval_seconds
                    )
                except TimeoutError:
                    pass
    finally:
        await redis.aclose()


if __name__ == "__main__":
    asyncio.run(run())
