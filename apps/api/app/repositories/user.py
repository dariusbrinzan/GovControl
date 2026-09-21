import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class UserRepository:
    """Persistence operations for tenant-scoped users."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id_for_tenant(self, user_id: uuid.UUID, tenant_id: uuid.UUID) -> User | None:
        user: User | None = await self._session.scalar(
            select(User).where(User.id == user_id, User.tenant_id == tenant_id)
        )
        return user

    async def list_for_tenant(self, tenant_id: uuid.UUID) -> list[User]:
        users = await self._session.scalars(
            select(User).where(User.tenant_id == tenant_id).order_by(User.display_name, User.id)
        )
        return list(users)

    def add(self, user: User) -> None:
        self._session.add(user)
