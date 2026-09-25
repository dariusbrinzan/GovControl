import asyncio
import json
import logging
import signal
from datetime import UTC, date, datetime, timedelta
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError

from contracts_app.config import get_settings
from contracts_app.database import session_factory
from contracts_app.models import (
    ContractMilestone,
    ContractNotification,
    ContractObligation,
    ContractPayment,
    MilestoneStatus,
    ObligationStatus,
    OutboxEvent,
    PaymentStatus,
)

logger = logging.getLogger("govcontracts.worker")


def log_event(event: str, **details: Any) -> None:
    logger.info(json.dumps({"event": event, "service": "govcontracts-worker", **details}))


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
                stream,
                {"event": json.dumps(event_envelope(event), separators=(",", ":"))},
            )
            event.published_at = datetime.now(UTC)
        return len(events)


async def create_due_reminders(today: date, horizon_days: int = 14) -> int:
    horizon = today + timedelta(days=horizon_days)
    async with session_factory() as session, session.begin():
        milestone_rows = (
            await session.execute(
                select(
                    ContractMilestone.tenant_id,
                    ContractMilestone.id,
                    ContractMilestone.title,
                    ContractMilestone.due_date,
                ).where(
                    ContractMilestone.due_date.between(today, horizon),
                    ContractMilestone.status.not_in(
                        [MilestoneStatus.COMPLETED, MilestoneStatus.CANCELLED]
                    ),
                )
            )
        ).all()
        obligation_rows = (
            await session.execute(
                select(
                    ContractObligation.tenant_id,
                    ContractObligation.id,
                    ContractObligation.description,
                    ContractObligation.due_date,
                ).where(
                    ContractObligation.due_date.between(today, horizon),
                    ContractObligation.status.not_in(
                        [ObligationStatus.COMPLETED, ObligationStatus.CANCELLED]
                    ),
                )
            )
        ).all()
        payment_rows = (
            await session.execute(
                select(
                    ContractPayment.tenant_id,
                    ContractPayment.id,
                    ContractPayment.reference,
                    ContractPayment.due_date,
                ).where(
                    ContractPayment.due_date.between(today, horizon),
                    ContractPayment.status.not_in(
                        [PaymentStatus.PAID, PaymentStatus.REJECTED, PaymentStatus.CANCELLED]
                    ),
                )
            )
        ).all()
        values: list[dict[str, Any]] = []
        for tenant_id, entity_id, title, due_date in milestone_rows:
            values.append(
                {
                    "tenant_id": tenant_id,
                    "entity_type": "ContractMilestone",
                    "entity_id": entity_id,
                    "notification_type": "DUE_SOON",
                    "title": "Jalon contractual apropiat",
                    "body": f"{title} are termen la {due_date.isoformat()}.",
                    "due_date": due_date,
                }
            )
        for tenant_id, entity_id, description, obligation_due_date in obligation_rows:
            if obligation_due_date is None:
                continue
            values.append(
                {
                    "tenant_id": tenant_id,
                    "entity_type": "ContractObligation",
                    "entity_id": entity_id,
                    "notification_type": "DUE_SOON",
                    "title": "Obligație contractuală apropiată",
                    "body": f"{description} are termen la {obligation_due_date.isoformat()}.",
                    "due_date": obligation_due_date,
                }
            )
        for tenant_id, entity_id, reference, payment_due_date in payment_rows:
            payment_label = reference or "Plata planificată"
            values.append(
                {
                    "tenant_id": tenant_id,
                    "entity_type": "ContractPayment",
                    "entity_id": entity_id,
                    "notification_type": "DUE_SOON",
                    "title": "Plată contractuală apropiată",
                    "body": f"{payment_label} are scadența la {payment_due_date.isoformat()}.",
                    "due_date": payment_due_date,
                }
            )
        if not values:
            return 0
        await session.execute(
            insert(ContractNotification)
            .values(values)
            .on_conflict_do_nothing(constraint="uq_contract_notifications_business_key")
        )
        return len(values)


async def run_worker() -> None:
    settings = get_settings()
    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, stopped.set)
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    last_reminder_scan = 0.0
    log_event("worker_started", stream=settings.event_stream_name)
    try:
        while not stopped.is_set():
            try:
                current_time = loop.time()
                if current_time - last_reminder_scan >= settings.reminder_scan_interval_seconds:
                    reminders = await create_due_reminders(date.today())
                    last_reminder_scan = current_time
                    if reminders:
                        log_event("reminders_scanned", candidates=reminders)
                published = await publish_batch(
                    redis, settings.outbox_batch_size, settings.event_stream_name
                )
                if published:
                    log_event("outbox_published", count=published)
            except (RedisError, SQLAlchemyError) as exc:
                logger.exception(
                    json.dumps(
                        {
                            "event": "worker_dependency_error",
                            "service": "govcontracts-worker",
                            "error_type": type(exc).__name__,
                        }
                    )
                )
                published = 0
            if published == 0:
                try:
                    await asyncio.wait_for(
                        stopped.wait(), timeout=settings.outbox_poll_interval_seconds
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
