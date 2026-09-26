import asyncio
import json
import logging
import signal
from datetime import UTC, datetime
from tempfile import SpooledTemporaryFile
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from documents_app.config import get_settings
from documents_app.database import session_factory
from documents_app.models import (
    Document,
    DocumentAuditEvent,
    DocumentState,
    DocumentVersion,
    OutboxEvent,
)
from documents_app.scanner import ScanError, scanner_from_settings
from documents_app.storage import S3Storage, StorageError

logger = logging.getLogger("govdocuments.worker")


def log_event(event: str, **details: Any) -> None:
    logger.info(json.dumps({"event": event, "service": "govdocuments-worker", **details}))


def event_envelope(event: OutboxEvent) -> dict[str, Any]:
    return {
        "id": str(event.id),
        "type": event.event_type,
        "tenant_id": str(event.tenant_id),
        "aggregate_type": event.aggregate_type,
        "aggregate_id": str(event.aggregate_id),
        "occurred_at": event.created_at.isoformat(),
        "payload": event.payload,
    }


async def scan_batch(storage: S3Storage, batch_size: int = 10) -> int:
    settings = get_settings()
    scanner = scanner_from_settings(settings)
    async with session_factory() as session:
        versions = list(
            await session.scalars(
                select(DocumentVersion)
                .where(DocumentVersion.state == DocumentState.QUARANTINED)
                .order_by(DocumentVersion.created_at, DocumentVersion.id)
                .with_for_update(skip_locked=True)
                .limit(batch_size)
            )
        )
        for version in versions:
            version.state = DocumentState.SCANNING
        await session.commit()
    for version in versions:
        clean = False
        reason: str | None = None
        try:
            with SpooledTemporaryFile(max_size=2 * 1024 * 1024) as content:
                await run_in_threadpool(storage.download_to, version.storage_key, content)
                clean, reason = await run_in_threadpool(scanner.scan, content)
        except (StorageError, ScanError) as exc:
            log_event("scan_dependency_error", error_type=type(exc).__name__)
            async with session_factory() as session, session.begin():
                current = await session.get(DocumentVersion, version.id)
                if current is not None:
                    current.state = DocumentState.QUARANTINED
            continue
        async with session_factory() as session, session.begin():
            current = await session.get(DocumentVersion, version.id)
            document = await session.get(Document, version.document_id)
            if current is None or document is None:
                continue
            current.state = DocumentState.AVAILABLE if clean else DocumentState.REJECTED
            current.rejection_reason = reason
            current.scanned_at = datetime.now(UTC)
            if document.current_version_number == current.version_number:
                document.state = current.state
            action = "document.scan_clean" if clean else "document.scan_rejected"
            event_type = "document.available.v1" if clean else "document.rejected.v1"
            session.add(
                DocumentAuditEvent(
                    tenant_id=document.tenant_id,
                    document_id=document.id,
                    actor_user_id=current.created_by_user_id,
                    action=action,
                    payload={"version_id": str(current.id), "reason": reason},
                )
            )
            session.add(
                OutboxEvent(
                    tenant_id=document.tenant_id,
                    event_type=event_type,
                    aggregate_type="Document",
                    aggregate_id=document.id,
                    payload={"version_id": str(current.id)},
                )
            )
    return len(versions)


async def publish_batch(redis: Redis, batch_size: int, stream: str) -> int:
    async with session_factory() as session, session.begin():
        events = list(
            await session.scalars(
                select(OutboxEvent)
                .where(OutboxEvent.published_at.is_(None))
                .order_by(OutboxEvent.created_at, OutboxEvent.id)
                .with_for_update(skip_locked=True)
                .limit(batch_size)
            )
        )
        for event in events:
            await redis.xadd(
                stream, {"event": json.dumps(event_envelope(event), separators=(",", ":"))}
            )
            event.published_at = datetime.now(UTC)
        return len(events)


async def run_worker() -> None:
    settings = get_settings()
    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, stopped.set)
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    storage = S3Storage(settings)
    log_event("worker_started", stream=settings.event_stream_name)
    try:
        while not stopped.is_set():
            work = 0
            try:
                work += await scan_batch(storage)
                work += await publish_batch(
                    redis, settings.outbox_batch_size, settings.event_stream_name
                )
            except (RedisError, SQLAlchemyError, StorageError, ScanError) as exc:
                logger.exception(
                    json.dumps(
                        {
                            "event": "worker_dependency_error",
                            "service": "govdocuments-worker",
                            "error_type": type(exc).__name__,
                        }
                    )
                )
            if work == 0:
                try:
                    await asyncio.wait_for(
                        stopped.wait(), timeout=settings.worker_poll_interval_seconds
                    )
                except TimeoutError:
                    pass
    finally:
        await redis.aclose()
        log_event("worker_stopped")


def main() -> None:
    settings = get_settings()
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
