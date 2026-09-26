import asyncio
import json
import logging
import signal
import uuid
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
    Contract,
    ContractMilestone,
    ContractObligation,
    ContractPayment,
    MilestoneStatus,
    ObligationStatus,
    OutboxEvent,
    PaymentStatus,
)

logger = logging.getLogger("govcontracts.worker")
REMINDER_NAMESPACE = uuid.UUID("83a5fa53-871f-4a89-bfc6-97737c667f85")


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
                    ContractMilestone.due_date,
                    Contract.responsible_user_id,
                    Contract.created_by,
                )
                .join(Contract, Contract.id == ContractMilestone.contract_id)
                .where(
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
                    ContractObligation.due_date,
                    ContractObligation.responsible_user_id,
                    Contract.responsible_user_id,
                    Contract.created_by,
                )
                .join(Contract, Contract.id == ContractObligation.contract_id)
                .where(
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
                    ContractPayment.due_date,
                    Contract.responsible_user_id,
                    Contract.created_by,
                )
                .join(Contract, Contract.id == ContractPayment.contract_id)
                .where(
                    ContractPayment.due_date.between(today, horizon),
                    ContractPayment.status.not_in(
                        [PaymentStatus.PAID, PaymentStatus.REJECTED, PaymentStatus.CANCELLED]
                    ),
                )
            )
        ).all()
        values: list[dict[str, Any]] = []
        for tenant_id, entity_id, due_date, responsible_user_id, created_by in milestone_rows:
            recipient_id = responsible_user_id or created_by
            event_id = uuid.uuid5(
                REMINDER_NAMESPACE, f"milestone:{entity_id}:{due_date.isoformat()}"
            )
            values.append(
                {
                    "id": event_id,
                    "tenant_id": tenant_id,
                    "event_type": "contracts.reminder.milestone-due.v1",
                    "aggregate_type": "ContractMilestone",
                    "aggregate_id": entity_id,
                    "payload": {
                        "milestone_id": str(entity_id),
                        "recipient_user_id": str(recipient_id),
                        "due_date": due_date.isoformat(),
                    },
                }
            )
        for (
            tenant_id,
            entity_id,
            obligation_due_date,
            obligation_user_id,
            contract_user_id,
            created_by,
        ) in obligation_rows:
            if obligation_due_date is None:
                continue
            recipient_id = obligation_user_id or contract_user_id or created_by
            event_id = uuid.uuid5(
                REMINDER_NAMESPACE,
                f"obligation:{entity_id}:{obligation_due_date.isoformat()}",
            )
            values.append(
                {
                    "id": event_id,
                    "tenant_id": tenant_id,
                    "event_type": "contracts.reminder.obligation-due.v1",
                    "aggregate_type": "ContractObligation",
                    "aggregate_id": entity_id,
                    "payload": {
                        "obligation_id": str(entity_id),
                        "recipient_user_id": str(recipient_id),
                        "due_date": obligation_due_date.isoformat(),
                    },
                }
            )
        for tenant_id, entity_id, payment_due_date, responsible_user_id, created_by in payment_rows:
            recipient_id = responsible_user_id or created_by
            event_id = uuid.uuid5(
                REMINDER_NAMESPACE, f"payment:{entity_id}:{payment_due_date.isoformat()}"
            )
            values.append(
                {
                    "id": event_id,
                    "tenant_id": tenant_id,
                    "event_type": "contracts.reminder.payment-due.v1",
                    "aggregate_type": "ContractPayment",
                    "aggregate_id": entity_id,
                    "payload": {
                        "payment_id": str(entity_id),
                        "recipient_user_id": str(recipient_id),
                        "due_date": payment_due_date.isoformat(),
                    },
                }
            )
        if not values:
            return 0
        inserted = await session.scalars(
            insert(OutboxEvent)
            .values(values)
            .on_conflict_do_nothing(index_elements=["id"])
            .returning(OutboxEvent.id)
        )
        return len(inserted.all())


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
