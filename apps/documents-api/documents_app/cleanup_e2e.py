import asyncio
import json
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import delete, or_, select
from starlette.concurrency import run_in_threadpool

from documents_app.config import Settings, get_settings
from documents_app.database import session_factory
from documents_app.models import (
    Document,
    DocumentAuditEvent,
    DocumentVersion,
    OutboxEvent,
)
from documents_app.storage import S3Storage


async def cleanup_events(settings: Settings, removed_ids: set[str]) -> int:
    async with session_factory() as session:
        retained_ids = {
            str(document_id) for document_id in await session.scalars(select(Document.id))
        }
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        entries: list[tuple[str, dict[str, Any]]] = await redis.xrange(
            settings.event_stream_name
        )
        stream_ids = []
        for stream_id, fields in entries:
            try:
                envelope = json.loads(str(fields.get("event", "{}")))
            except json.JSONDecodeError:
                continue
            aggregate_id = str(envelope.get("aggregate_id", ""))
            if str(envelope.get("type", "")).startswith("document.") and (
                aggregate_id in removed_ids or aggregate_id not in retained_ids
            ):
                stream_ids.append(stream_id)
        if not stream_ids:
            return 0
        return int(await redis.xdel(settings.event_stream_name, *stream_ids))
    finally:
        await redis.aclose()


async def cleanup() -> dict[str, int]:
    settings = get_settings()
    if settings.app_env != "development":
        raise RuntimeError("E2E cleanup is allowed only in development.")
    storage = S3Storage(settings)
    async with session_factory() as session:
        document_ids = list(
            await session.scalars(
                select(Document.id)
                .join(DocumentVersion, DocumentVersion.document_id == Document.id)
                .where(
                    or_(
                        DocumentVersion.safe_filename.like("e2e-%"),
                        Document.category.in_(("PERFORMANCE_SMOKE", "SMOKE_TEST")),
                    )
                )
                .distinct()
            )
        )
        storage_keys: list[str] = []
        if document_ids:
            storage_keys = list(
                await session.scalars(
                    select(DocumentVersion.storage_key).where(
                        DocumentVersion.document_id.in_(document_ids)
                    )
                )
            )
            await session.execute(
                delete(DocumentAuditEvent).where(
                    DocumentAuditEvent.document_id.in_(document_ids)
                )
            )
            await session.execute(
                delete(OutboxEvent).where(OutboxEvent.aggregate_id.in_(document_ids))
            )
            await session.execute(delete(Document).where(Document.id.in_(document_ids)))
            await session.commit()
    removed_events = await cleanup_events(
        settings, {str(document_id) for document_id in document_ids}
    )
    for storage_key in storage_keys:
        await run_in_threadpool(storage.delete, storage_key)
    return {
        "documents": len(document_ids),
        "events": removed_events,
        "objects": len(storage_keys),
    }


def main() -> None:
    print(json.dumps(asyncio.run(cleanup()), sort_keys=True))


if __name__ == "__main__":
    main()
