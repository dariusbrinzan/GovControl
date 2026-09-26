import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.legal import LegalObligation
from app.models.notification import Notification, NotificationStatus
from app.models.outbox import IntegrationOutboxEvent
from app.repositories.legal import LegalRepository
from app.repositories.notification import NotificationRepository
from app.services.audit import AuditService
from app.services.deadlines import DeadlineState, deadline_state


class NotificationChannel(StrEnum):
    IN_APP = "IN_APP"
    EMAIL = "EMAIL"


@dataclass(frozen=True)
class NotificationMessage:
    recipient: str
    subject: str
    body: str
    channel: NotificationChannel


class NotificationProvider:
    async def send(self, message: NotificationMessage) -> None:
        raise NotImplementedError


class InMemoryNotificationProvider(NotificationProvider):
    """Development provider used until an external delivery channel is configured."""

    def __init__(self) -> None:
        self.messages: list[NotificationMessage] = []

    async def send(self, message: NotificationMessage) -> None:
        self.messages.append(message)


class NotificationNotFoundError(Exception):
    pass


class NotificationService:
    """Creates in-app deadline alerts; external delivery stays behind NotificationProvider."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = NotificationRepository(session)
        self.legal = LegalRepository(session)
        self.audit = AuditService(session)

    async def list_for_user(self, tenant_id: uuid.UUID, user_id: uuid.UUID) -> list[Notification]:
        return await self.repo.list_for_user(tenant_id, user_id)

    async def mark_read(
        self, tenant_id: uuid.UUID, user_id: uuid.UUID, notification_id: uuid.UUID
    ) -> Notification:
        notification = await self.repo.get_for_user(notification_id, tenant_id, user_id)
        if notification is None:
            raise NotificationNotFoundError
        if notification.status == NotificationStatus.UNREAD:
            notification.status = NotificationStatus.READ
            notification.read_at = datetime.now(UTC)
            self.audit.record_event(
                tenant_id=tenant_id,
                actor_user_id=user_id,
                action="MARKED_READ",
                entity_type="Notification",
                entity_id=notification.id,
            )
            await self.session.commit()
            await self.session.refresh(notification)
        return notification

    async def dispatch_deadline_reminders(
        self, tenant_id: uuid.UUID, actor_id: uuid.UUID, today: date
    ) -> int:
        candidates: list[tuple[LegalObligation, DeadlineState, str]] = []
        for obligation in await self.legal.obligations(tenant_id):
            state = deadline_state(obligation.due_date, obligation.status, today)
            if state not in {DeadlineState.OVERDUE, DeadlineState.DUE_TODAY} and not (
                state == DeadlineState.UPCOMING
                and obligation.due_date is not None
                and (obligation.due_date - today).days <= 7
            ):
                continue
            if obligation.due_date is None:
                continue
            key = f"deadline:{obligation.id}:{today.isoformat()}:{state.value}"
            candidates.append((obligation, state, key))

        values: list[dict[str, object]] = []
        for obligation, state, key in candidates:
            if obligation.due_date is None:
                continue
            event_id = uuid.uuid5(
                uuid.UUID("96ce90a0-8d50-4f50-a4d0-957aa309169d"), key
            )
            values.append(
                {
                    "id": event_id,
                    "tenant_id": tenant_id,
                    "event_type": (
                        "legal.deadline.overdue.v1"
                        if state == DeadlineState.OVERDUE
                        else "legal.deadline.due-soon.v1"
                    ),
                    "aggregate_type": "LegalObligation",
                    "aggregate_id": obligation.id,
                    "payload": {
                        "obligation_id": str(obligation.id),
                        "recipient_user_id": str(obligation.responsible_user_id or actor_id),
                        "due_date": obligation.due_date.isoformat(),
                    },
                }
            )
        if not values:
            return 0
        inserted = await self.session.scalars(
            insert(IntegrationOutboxEvent)
            .values(values)
            .on_conflict_do_nothing(index_elements=["id"])
            .returning(IntegrationOutboxEvent.id)
        )
        await self.session.commit()
        return len(inserted.all())

    @staticmethod
    def _deadline_title(state: DeadlineState) -> str:
        if state == DeadlineState.OVERDUE:
            return "Termen depășit"
        if state == DeadlineState.DUE_TODAY:
            return "Termen scadent astăzi"
        return "Termen în următoarele 7 zile"
