import os
import time
import uuid
from datetime import UTC, datetime, timedelta

import fakeredis.aioredis
import httpx
import pytest
from sqlalchemy import delete, select

from notifications_app.backfill import LegacyNotification, backfill
from notifications_app.config import Settings
from notifications_app.database import session_factory
from notifications_app.models import (
    Channel,
    DeliveryAttempt,
    Notification,
    NotificationAuditEvent,
    NotificationPreference,
    NotificationRecipient,
    NotificationSchedule,
    NotificationStatus,
    OutboxEvent,
    ProcessedEvent,
    Severity,
)
from notifications_app.scheduler import process_deliveries
from notifications_app.schemas import (
    InternalNotificationCreate,
    InternalScheduleCreate,
    PreferenceInput,
)
from notifications_app.service import NotificationService

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("GOVCONTROL_INTEGRATION") != "1",
        reason="set GOVCONTROL_INTEGRATION=1 with migrated PostgreSQL",
    ),
]


async def cleanup(tenant_ids: set[uuid.UUID], event_ids: set[uuid.UUID]) -> None:
    async with session_factory() as session:
        for model in (
            DeliveryAttempt,
            NotificationRecipient,
            NotificationPreference,
            NotificationSchedule,
            NotificationAuditEvent,
            OutboxEvent,
            Notification,
        ):
            await session.execute(delete(model).where(model.tenant_id.in_(tenant_ids)))
        if event_ids:
            await session.execute(
                delete(ProcessedEvent).where(ProcessedEvent.event_id.in_(event_ids))
            )
        await session.commit()


def event(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    event_id: uuid.UUID,
    *,
    resource_id: uuid.UUID | None = None,
) -> InternalNotificationCreate:
    resource_id = resource_id or uuid.uuid4()
    return InternalNotificationCreate(
        event_id=event_id,
        event_type="document.available.v1",
        tenant_id=tenant_id,
        recipient_user_id=user_id,
        resource_type="Document",
        resource_id=resource_id,
        template_key="document.available",
        variables={"resource_id": str(resource_id), "action": "available"},
        deduplication_key=f"integration:{event_id}",
    )


async def test_inbox_filters_mutations_isolation_dedup_and_safe_outbox() -> None:
    tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()
    user_a, user_b = uuid.uuid4(), uuid.uuid4()
    event_ids = {uuid.uuid4(), uuid.uuid4(), uuid.uuid4()}
    try:
        async with session_factory() as session:
            service = NotificationService(session)
            first, created = await service.ingest(event(tenant_a, user_a, next(iter(event_ids))))
            assert created is True
            _, duplicate_created = await service.ingest(
                event(tenant_a, user_a, first.source_event_id)  # type: ignore[arg-type]
            )
            assert duplicate_created is False
            remaining = event_ids - {first.source_event_id}
            await service.ingest(event(tenant_a, user_b, remaining.pop()))
            await service.ingest(event(tenant_b, user_a, remaining.pop()))

            items, total = await service.page(
                tenant_a,
                user_a,
                limit=1,
                offset=0,
                status=NotificationStatus.UNREAD,
                category="DOCUMENTS",
                severity="SUCCESS",
                created_from=None,
                created_to=None,
            )
            assert total == 1
            assert [item.id for item in items] == [first.id]
            assert await service.unread_count(tenant_a, user_a) == 1
            assert await service.unread_count(tenant_a, user_b) == 1
            assert await service.unread_count(tenant_b, user_a) == 1

            await service.set_status(
                tenant_a, user_a, first.id, NotificationStatus.ARCHIVED
            )
            assert await service.unread_count(tenant_a, user_a) == 0
            await service.set_status(tenant_a, user_a, first.id, NotificationStatus.UNREAD)
            assert await service.mark_all_read(tenant_a, user_a) == 1

            outbox_payloads = list(
                await session.scalars(
                    select(OutboxEvent.payload).where(OutboxEvent.tenant_id == tenant_a)
                )
            )
            serialized = str(outbox_payloads).lower()
            assert "title" not in serialized
            assert "body" not in serialized

            schedule_input = InternalScheduleCreate(
                tenant_id=tenant_a,
                recipient_user_id=user_a,
                template_key="legal.deadline",
                variables={"resource_id": str(uuid.uuid4()), "action": "due soon"},
                resource_type="LegalObligation",
                resource_id=uuid.uuid4(),
                scheduled_for=datetime.now(UTC) + timedelta(hours=1),
                deduplication_key=f"integration-schedule:{tenant_a}",
            )
            scheduled, schedule_created = await service.schedule(schedule_input)
            repeated, repeated_created = await service.schedule(schedule_input)
            assert schedule_created is True
            assert repeated_created is False
            assert repeated.id == scheduled.id
    finally:
        await cleanup({tenant_a, tenant_b}, event_ids)


async def test_preference_suppression_and_backfill_are_idempotent() -> None:
    tenant_id, user_id, event_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    legacy_id = uuid.uuid4()
    try:
        async with session_factory() as session:
            service = NotificationService(session)
            await service.set_preference(
                tenant_id,
                user_id,
                PreferenceInput(category="DOCUMENTS", channel=Channel.IN_APP, enabled=False),
            )
            notification, created = await service.ingest(event(tenant_id, user_id, event_id))
            assert created is True
            assert await service.unread_count(tenant_id, user_id) == 0
            recipient = await session.scalar(
                select(NotificationRecipient).where(
                    NotificationRecipient.notification_id == notification.id
                )
            )
            assert recipient is None

        legacy = LegacyNotification(
            source="platform",
            legacy_id=legacy_id,
            tenant_id=tenant_id,
            recipient_user_id=user_id,
            resource_type="LegalObligation",
            resource_id=uuid.uuid4(),
            category="LEGAL",
            severity=Severity.WARNING,
            title="Legacy controlled title",
            body="Legacy controlled body",
            status=NotificationStatus.READ,
            read_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
        )
        first = await backfill([legacy])
        second = await backfill([legacy])
        assert first == {"source": 1, "imported": 1, "skipped": 0, "verified": 1}
        assert second == {"source": 1, "imported": 0, "skipped": 1, "verified": 1}
    finally:
        await cleanup({tenant_id}, {event_id})


async def test_local_email_delivery_is_opt_in_and_audited(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id, user_id, event_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    settings = Settings(
        notifications_database_url="postgresql+asyncpg://unused",
        email_enabled=True,
        email_adapter="local",
    )
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    try:
        async with session_factory() as session:
            service = NotificationService(session, settings)
            await service.set_preference(
                tenant_id,
                user_id,
                PreferenceInput(category="DOCUMENTS", channel=Channel.EMAIL, enabled=True),
            )
            notification, _ = await service.ingest(event(tenant_id, user_id, event_id))
        monkeypatch.setattr("notifications_app.scheduler.get_settings", lambda: settings)
        async with httpx.AsyncClient() as client:
            assert await process_deliveries(client, redis) >= 1
        async with session_factory() as session:
            delivery = await session.scalar(
                select(DeliveryAttempt).where(
                    DeliveryAttempt.notification_id == notification.id,
                    DeliveryAttempt.channel == Channel.EMAIL,
                )
            )
            assert delivery is not None
            assert str(delivery.status) == "DELIVERED"
            actions = set(
                await session.scalars(
                    select(NotificationAuditEvent.action).where(
                        NotificationAuditEvent.tenant_id == tenant_id
                    )
                )
            )
            assert "DELIVERY_SUCCEEDED" in actions
    finally:
        await redis.aclose()
        await cleanup({tenant_id}, {event_id})


async def test_local_duplicate_burst_remains_idempotent() -> None:
    tenant_id, user_id = uuid.uuid4(), uuid.uuid4()
    event_ids = {uuid.uuid4() for _ in range(40)}
    started = time.perf_counter()
    try:
        async with session_factory() as session:
            service = NotificationService(session)
            values = [event(tenant_id, user_id, event_id) for event_id in event_ids]
            for value in values:
                _, created = await service.ingest(value)
                assert created is True
            for value in values:
                _, created = await service.ingest(value)
                assert created is False
            count = len(
                list(
                    await session.scalars(
                        select(Notification.id).where(Notification.tenant_id == tenant_id)
                    )
                )
            )
            assert count == len(event_ids)
        assert time.perf_counter() - started < 30
    finally:
        await cleanup({tenant_id}, event_ids)
