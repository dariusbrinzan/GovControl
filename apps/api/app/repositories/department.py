import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.department import Department


class DepartmentRepository:
    """Persistence operations for tenant-owned departments."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id_for_tenant(
        self,
        department_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> Department | None:
        department: Department | None = await self._session.scalar(
            select(Department).where(
                Department.id == department_id,
                Department.tenant_id == tenant_id,
            )
        )
        return department

    async def list_for_tenant(self, tenant_id: uuid.UUID) -> list[Department]:
        departments = await self._session.scalars(
            select(Department)
            .where(Department.tenant_id == tenant_id)
            .order_by(Department.name, Department.id)
        )
        return list(departments)

    def add(self, department: Department) -> None:
        self._session.add(department)
