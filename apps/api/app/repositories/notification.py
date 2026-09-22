import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification


class NotificationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_for_user(self, tenant_id: uuid.UUID, user_id: uuid.UUID) -> list[Notification]:
        return list(
            await self.session.scalars(
                select(Notification)
                .where(
                    Notification.tenant_id == tenant_id,
                    Notification.recipient_user_id == user_id,
                )
                .order_by(Notification.created_at.desc())
            )
        )

    async def get_for_user(
        self, notification_id: uuid.UUID, tenant_id: uuid.UUID, user_id: uuid.UUID
    ) -> Notification | None:
        item: Notification | None = await self.session.scalar(
            select(Notification).where(
                Notification.id == notification_id,
                Notification.tenant_id == tenant_id,
                Notification.recipient_user_id == user_id,
            )
        )
        return item

    async def existing_deduplication_keys(
        self, tenant_id: uuid.UUID, keys: set[str]
    ) -> set[str]:
        if not keys:
            return set()
        rows = await self.session.scalars(
            select(Notification.deduplication_key).where(
                Notification.tenant_id == tenant_id,
                Notification.deduplication_key.in_(keys),
            )
        )
        return set(rows)
