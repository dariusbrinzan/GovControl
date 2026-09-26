import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from notifications_app.config import Settings, get_settings
from notifications_app.models import (
    Channel,
    DeliveryAttempt,
    DeliveryStatus,
    Notification,
    NotificationAuditEvent,
    NotificationPreference,
    NotificationRecipient,
    NotificationSchedule,
    NotificationStatus,
    NotificationTemplate,
    OutboxEvent,
    ProcessedEvent,
)
from notifications_app.observability import current_request_id
from notifications_app.schemas import (
    InternalNotificationCreate,
    InternalScheduleCreate,
    NotificationItem,
    PreferenceInput,
)
from notifications_app.templates import TemplateValidationError, render_template, validate_template


class NotificationNotFoundError(Exception):
    pass


class NotificationConflictError(Exception):
    pass


class NotificationService:
    def __init__(self, session: AsyncSession, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()

    async def page(
        self,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        limit: int,
        offset: int,
        status: NotificationStatus | None,
        category: str | None,
        severity: str | None,
        created_from: datetime | None,
        created_to: datetime | None,
    ) -> tuple[list[NotificationItem], int]:
        filters: list[Any] = [
            NotificationRecipient.tenant_id == tenant_id,
            NotificationRecipient.user_id == user_id,
            Notification.tenant_id == tenant_id,
        ]
        if status is not None:
            filters.append(NotificationRecipient.status == status)
        if category:
            filters.append(Notification.category == category)
        if severity:
            filters.append(Notification.severity == severity)
        if created_from:
            filters.append(Notification.created_at >= created_from)
        if created_to:
            filters.append(Notification.created_at <= created_to)
        base = (
            select(Notification, NotificationRecipient)
            .join(NotificationRecipient, NotificationRecipient.notification_id == Notification.id)
            .where(*filters)
        )
        total = int(
            await self.session.scalar(
                select(func.count()).select_from(base.order_by(None).subquery())
            )
            or 0
        )
        rows = (
            await self.session.execute(
                base.order_by(Notification.created_at.desc(), Notification.id)
                .offset(offset)
                .limit(limit)
            )
        ).all()
        return [self._item(notification, recipient) for notification, recipient in rows], total

    async def unread_count(self, tenant_id: uuid.UUID, user_id: uuid.UUID) -> int:
        return int(
            await self.session.scalar(
                select(func.count())
                .select_from(NotificationRecipient)
                .where(
                    NotificationRecipient.tenant_id == tenant_id,
                    NotificationRecipient.user_id == user_id,
                    NotificationRecipient.status == NotificationStatus.UNREAD,
                )
            )
            or 0
        )

    async def set_status(
        self,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        notification_id: uuid.UUID,
        status: NotificationStatus,
        audit_action: str | None = None,
    ) -> NotificationItem:
        row = (
            await self.session.execute(
                select(Notification, NotificationRecipient)
                .join(
                    NotificationRecipient,
                    NotificationRecipient.notification_id == Notification.id,
                )
                .where(
                    Notification.id == notification_id,
                    Notification.tenant_id == tenant_id,
                    NotificationRecipient.tenant_id == tenant_id,
                    NotificationRecipient.user_id == user_id,
                )
                .with_for_update()
            )
        ).one_or_none()
        if row is None:
            raise NotificationNotFoundError
        notification, recipient = row
        now = datetime.now(UTC)
        recipient.status = status
        recipient.read_at = now if status == NotificationStatus.READ else None
        recipient.archived_at = now if status == NotificationStatus.ARCHIVED else None
        action = audit_action or {
            NotificationStatus.READ: "READ",
            NotificationStatus.UNREAD: "UNREAD",
            NotificationStatus.ARCHIVED: "ARCHIVED",
        }[status]
        self._audit(tenant_id, user_id, notification_id, action)
        if status in {NotificationStatus.READ, NotificationStatus.ARCHIVED}:
            self._outbox(
                tenant_id,
                notification_id,
                f"notification.{status.value.lower()}.v1",
                {"notification_id": str(notification_id), "recipient_user_id": str(user_id)},
            )
        await self.session.commit()
        return self._item(notification, recipient)

    async def mark_all_read(self, tenant_id: uuid.UUID, user_id: uuid.UUID) -> int:
        result = await self.session.scalars(
            update(NotificationRecipient)
            .where(
                NotificationRecipient.tenant_id == tenant_id,
                NotificationRecipient.user_id == user_id,
                NotificationRecipient.status == NotificationStatus.UNREAD,
            )
            .values(status=NotificationStatus.READ, read_at=datetime.now(UTC))
            .returning(NotificationRecipient.id)
        )
        count = len(result.all())
        if count:
            self._audit(tenant_id, user_id, None, "MARK_ALL_READ", {"count": count})
        await self.session.commit()
        return count

    async def preferences(
        self, tenant_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[NotificationPreference]:
        return list(
            await self.session.scalars(
                select(NotificationPreference)
                .where(
                    NotificationPreference.tenant_id == tenant_id,
                    NotificationPreference.user_id == user_id,
                )
                .order_by(NotificationPreference.category, NotificationPreference.channel)
            )
        )

    async def set_preference(
        self, tenant_id: uuid.UUID, user_id: uuid.UUID, value: PreferenceInput
    ) -> NotificationPreference:
        statement = (
            insert(NotificationPreference)
            .values(tenant_id=tenant_id, user_id=user_id, **value.model_dump())
            .on_conflict_do_update(
                constraint="uq_preference",
                set_={
                    "enabled": value.enabled,
                    "quiet_hours_start": value.quiet_hours_start,
                    "quiet_hours_end": value.quiet_hours_end,
                    "updated_at": datetime.now(UTC),
                },
            )
            .returning(NotificationPreference)
        )
        item = (await self.session.scalars(statement)).one()
        self._audit(
            tenant_id,
            user_id,
            None,
            "PREFERENCE_UPDATED",
            {"category": value.category, "channel": value.channel.value, "enabled": value.enabled},
        )
        self._outbox(
            tenant_id,
            item.id,
            "notification.preference_updated.v1",
            {"preference_id": str(item.id), "user_id": str(user_id)},
        )
        await self.session.commit()
        return item

    async def templates(self) -> list[NotificationTemplate]:
        return list(
            await self.session.scalars(
                select(NotificationTemplate).order_by(
                    NotificationTemplate.key, NotificationTemplate.version.desc()
                )
            )
        )

    async def create_template(
        self,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        *,
        key: str,
        title_template: str,
        body_template: str,
        allowed_variables: list[str],
        default_category: str,
        default_severity: str,
    ) -> NotificationTemplate:
        validate_template(title_template, body_template, allowed_variables)
        current = int(
            await self.session.scalar(
                select(func.max(NotificationTemplate.version)).where(
                    NotificationTemplate.key == key
                )
            )
            or 0
        )
        await self.session.execute(
            update(NotificationTemplate)
            .where(NotificationTemplate.key == key, NotificationTemplate.active.is_(True))
            .values(active=False)
        )
        item = NotificationTemplate(
            key=key,
            version=current + 1,
            title_template=title_template,
            body_template=body_template,
            allowed_variables=allowed_variables,
            default_category=default_category,
            default_severity=default_severity,
            created_by_user_id=actor_id,
        )
        self.session.add(item)
        await self.session.flush()
        self._audit(
            tenant_id,
            actor_id,
            None,
            "TEMPLATE_VERSION_CREATED",
            {"template_key": key, "version": item.version},
        )
        await self.session.commit()
        await self.session.refresh(item)
        return item

    async def ingest(
        self, value: InternalNotificationCreate, stream_message_id: str = "internal"
    ) -> tuple[Notification, bool]:
        existing_event = await self.session.get(ProcessedEvent, value.event_id)
        if existing_event is not None:
            notification = await self.session.scalar(
                select(Notification).where(
                    Notification.tenant_id == value.tenant_id,
                    Notification.source_event_id == value.event_id,
                )
            )
            if notification is None:
                raise NotificationConflictError("Processed event has no notification.")
            self._audit(value.tenant_id, None, notification.id, "DEDUPLICATED")
            await self.session.commit()
            return notification, False
        template = await self.session.scalar(
            select(NotificationTemplate)
            .where(
                NotificationTemplate.key == value.template_key,
                NotificationTemplate.active.is_(True),
            )
            .order_by(NotificationTemplate.version.desc())
        )
        if template is None:
            raise NotificationNotFoundError("Template is not available.")
        title, body = render_template(
            template.title_template,
            template.body_template,
            template.allowed_variables,
            value.variables,
        )
        notification = Notification(
            tenant_id=value.tenant_id,
            category=template.default_category,
            severity=template.default_severity,
            title=title,
            body=body,
            resource_type=value.resource_type,
            resource_id=value.resource_id,
            resource_url=value.resource_url
            or self._resource_url(value.resource_type, value.resource_id),
            template_key=template.key,
            template_version=template.version,
            source_event_id=value.event_id,
            deduplication_key=value.deduplication_key,
        )
        self.session.add(notification)
        await self.session.flush()
        preference = await self.session.scalar(
            select(NotificationPreference).where(
                NotificationPreference.tenant_id == value.tenant_id,
                NotificationPreference.user_id == value.recipient_user_id,
                NotificationPreference.category == template.default_category,
                NotificationPreference.channel == Channel.IN_APP,
            )
        )
        in_app_enabled = preference is None or preference.enabled
        recipient = NotificationRecipient(
            notification_id=notification.id,
            tenant_id=value.tenant_id,
            user_id=value.recipient_user_id,
        )
        delivery = DeliveryAttempt(
            notification_id=notification.id,
            tenant_id=value.tenant_id,
            recipient_user_id=value.recipient_user_id,
            channel=Channel.IN_APP,
            status=DeliveryStatus.DELIVERED,
            attempt_count=1,
            delivered_at=datetime.now(UTC),
        )
        processed = ProcessedEvent(
            event_id=value.event_id,
            event_type=value.event_type,
            stream_message_id=stream_message_id,
        )
        self.session.add(processed)
        if in_app_enabled:
            self.session.add_all([recipient, delivery])
        email_preference = await self.session.scalar(
            select(NotificationPreference).where(
                NotificationPreference.tenant_id == value.tenant_id,
                NotificationPreference.user_id == value.recipient_user_id,
                NotificationPreference.category == template.default_category,
                NotificationPreference.channel == Channel.EMAIL,
            )
        )
        email_enabled = (
            self.settings.email_enabled
            and email_preference is not None
            and email_preference.enabled
        )
        if email_enabled:
            self.session.add(
                DeliveryAttempt(
                    notification_id=notification.id,
                    tenant_id=value.tenant_id,
                    recipient_user_id=value.recipient_user_id,
                    channel=Channel.EMAIL,
                    status=DeliveryStatus.PENDING,
                    attempt_count=0,
                    next_attempt_at=datetime.now(UTC),
                )
            )
        self._audit(value.tenant_id, None, notification.id, "CREATED")
        if in_app_enabled:
            self._audit(
                value.tenant_id, None, notification.id, "DELIVERED", {"channel": "IN_APP"}
            )
        else:
            self._audit(
                value.tenant_id,
                None,
                notification.id,
                "PREFERENCE_SUPPRESSED",
                {"channel": "IN_APP"},
            )
        self._outbox(
            value.tenant_id,
            notification.id,
            "notification.created.v1",
            {
                "notification_id": str(notification.id),
                "recipient_user_id": str(value.recipient_user_id),
                "category": notification.category,
            },
        )
        if in_app_enabled:
            self._outbox(
                value.tenant_id,
                notification.id,
                "notification.delivery_succeeded.v1",
                {"notification_id": str(notification.id), "channel": "IN_APP"},
            )
        await self.session.commit()
        await self.session.refresh(notification)
        return notification, True

    async def schedule(
        self, value: InternalScheduleCreate
    ) -> tuple[NotificationSchedule, bool]:
        statement = (
            insert(NotificationSchedule)
            .values(**value.model_dump())
            .on_conflict_do_nothing(constraint="uq_schedule_dedup")
            .returning(NotificationSchedule)
        )
        scheduled = (await self.session.scalars(statement)).one_or_none()
        created = scheduled is not None
        if scheduled is None:
            scheduled = await self.session.scalar(
                select(NotificationSchedule).where(
                    NotificationSchedule.tenant_id == value.tenant_id,
                    NotificationSchedule.deduplication_key == value.deduplication_key,
                )
            )
        if scheduled is None:
            raise NotificationConflictError("Schedule could not be created.")
        self._audit(
            value.tenant_id,
            None,
            None,
            "SCHEDULED" if created else "SCHEDULE_DEDUPLICATED",
            {
                "schedule_id": str(scheduled.id),
                "template_key": value.template_key,
            },
        )
        await self.session.commit()
        return scheduled, created

    async def audit_events(self, tenant_id: uuid.UUID, limit: int) -> list[NotificationAuditEvent]:
        return list(
            await self.session.scalars(
                select(NotificationAuditEvent)
                .where(NotificationAuditEvent.tenant_id == tenant_id)
                .order_by(NotificationAuditEvent.created_at.desc())
                .limit(limit)
            )
        )

    async def deliveries(self, tenant_id: uuid.UUID, limit: int) -> list[DeliveryAttempt]:
        return list(
            await self.session.scalars(
                select(DeliveryAttempt)
                .where(DeliveryAttempt.tenant_id == tenant_id)
                .order_by(DeliveryAttempt.updated_at.desc())
                .limit(limit)
            )
        )

    async def retry_delivery(
        self, tenant_id: uuid.UUID, delivery_id: uuid.UUID, actor_id: uuid.UUID
    ) -> bool:
        delivery = await self.session.scalar(
            select(DeliveryAttempt)
            .where(DeliveryAttempt.id == delivery_id, DeliveryAttempt.tenant_id == tenant_id)
            .with_for_update()
        )
        if delivery is None:
            raise NotificationNotFoundError
        if delivery.status not in {DeliveryStatus.FAILED, DeliveryStatus.DEAD_LETTER}:
            raise NotificationConflictError("Only failed deliveries can be retried.")
        delivery.status = DeliveryStatus.PENDING
        delivery.next_attempt_at = datetime.now(UTC)
        delivery.last_error_code = None
        self._audit(tenant_id, actor_id, delivery.notification_id, "RETRY_QUEUED")
        await self.session.commit()
        return True

    def _audit(
        self,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID | None,
        notification_id: uuid.UUID | None,
        action: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self.session.add(
            NotificationAuditEvent(
                tenant_id=tenant_id,
                actor_user_id=actor_id,
                notification_id=notification_id,
                action=action,
                request_id=current_request_id(),
                payload=payload,
            )
        )

    def _outbox(
        self,
        tenant_id: uuid.UUID,
        aggregate_id: uuid.UUID,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        self.session.add(
            OutboxEvent(
                tenant_id=tenant_id,
                event_type=event_type,
                aggregate_id=aggregate_id,
                payload=payload,
            )
        )

    @staticmethod
    def _item(notification: Notification, recipient: NotificationRecipient) -> NotificationItem:
        return NotificationItem(
            id=notification.id,
            category=notification.category,
            severity=notification.severity,
            title=notification.title,
            body=notification.body,
            resource_type=notification.resource_type,
            resource_id=notification.resource_id,
            resource_url=notification.resource_url,
            status=recipient.status,
            read_at=recipient.read_at,
            archived_at=recipient.archived_at,
            created_at=notification.created_at,
        )

    @staticmethod
    def _resource_url(resource_type: str | None, resource_id: uuid.UUID | None) -> str | None:
        if resource_id is None:
            return None
        roots = {
            "Contract": "/contracts",
            "ContractMilestone": "/contracts",
            "ContractObligation": "/contracts",
            "ContractPayment": "/contracts",
            "Document": "/legal/documents",
            "LegalCase": "/legal/cases",
            "LegalObligation": "/legal/obligations",
            "EnforcementProceeding": "/legal/enforcements",
            "PenaltyExposure": "/legal/penalties",
        }
        root = roots.get(resource_type or "")
        return f"{root}/{resource_id}" if root else None


__all__ = [
    "NotificationConflictError",
    "NotificationNotFoundError",
    "NotificationService",
    "TemplateValidationError",
]
