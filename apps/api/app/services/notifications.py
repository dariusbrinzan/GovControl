import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification, NotificationStatus
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
        created = 0
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
            if await self.repo.has_deduplication_key(tenant_id, key):
                continue
            notification = Notification(
                tenant_id=tenant_id,
                recipient_user_id=obligation.responsible_user_id or actor_id,
                entity_type="LegalObligation",
                entity_id=obligation.id,
                notification_type=f"DEADLINE_{state.value}",
                title=self._deadline_title(state),
                body=(
                    f"Obligația „{obligation.description}” are termenul "
                    f"{obligation.due_date.isoformat()}."
                ),
                due_date=obligation.due_date,
                deduplication_key=key,
            )
            self.session.add(notification)
            await self.session.flush()
            self.audit.record_created(
                tenant_id=tenant_id,
                actor_user_id=actor_id,
                entity_type="Notification",
                entity_id=notification.id,
                new_value={"notification_type": notification.notification_type},
            )
            created += 1
        if created:
            await self.session.commit()
        return created

    @staticmethod
    def _deadline_title(state: DeadlineState) -> str:
        if state == DeadlineState.OVERDUE:
            return "Termen depășit"
        if state == DeadlineState.DUE_TODAY:
            return "Termen scadent astăzi"
        return "Termen în următoarele 7 zile"
