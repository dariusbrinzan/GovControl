import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rbac import Role, RoleScope


class RoleRepository:
    """Read operations for roles visible within a tenant."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_visible_to_tenant(self, tenant_id: uuid.UUID) -> list[Role]:
        roles = await self._session.scalars(
            select(Role)
            .where(or_(Role.scope == RoleScope.SYSTEM, Role.tenant_id == tenant_id))
            .order_by(Role.scope, Role.name, Role.id)
        )
        return list(roles)

    async def get_visible_by_id(self, role_id: uuid.UUID, tenant_id: uuid.UUID) -> Role | None:
        role: Role | None = await self._session.scalar(
            select(Role).where(
                Role.id == role_id,
                or_(Role.scope == RoleScope.SYSTEM, Role.tenant_id == tenant_id),
            )
        )
        return role
