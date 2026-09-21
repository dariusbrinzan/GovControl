import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.department import Department
from app.models.rbac import Role
from app.models.tenant import Tenant
from app.repositories.department import DepartmentRepository
from app.repositories.role import RoleRepository
from app.repositories.tenant import TenantRepository
from app.schemas.platform import DepartmentCreate
from app.services.audit import AuditService


class InvalidParentDepartmentError(Exception):
    """Raised when a parent department is outside the caller's tenant."""


class DepartmentConflictError(Exception):
    """Raised when a department violates a tenant-level uniqueness constraint."""


class PlatformService:
    """Tenant-scoped platform administration use cases."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._department_repository = DepartmentRepository(session)
        self._role_repository = RoleRepository(session)
        self._tenant_repository = TenantRepository(session)
        self._audit_service = AuditService(session)

    async def get_tenant(self, tenant_id: uuid.UUID) -> Tenant | None:
        return await self._tenant_repository.get_by_id(tenant_id)

    async def list_departments(self, tenant_id: uuid.UUID) -> list[Department]:
        return await self._department_repository.list_for_tenant(tenant_id)

    async def create_department(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        department_data: DepartmentCreate,
    ) -> Department:
        if department_data.parent_department_id is not None:
            parent_department = await self._department_repository.get_by_id_for_tenant(
                department_data.parent_department_id,
                tenant_id,
            )
            if parent_department is None:
                raise InvalidParentDepartmentError

        department = Department(
            tenant_id=tenant_id,
            parent_department_id=department_data.parent_department_id,
            name=department_data.name,
            code=department_data.code,
        )
        self._department_repository.add(department)

        try:
            await self._session.flush()
            self._audit_service.record_created(
                tenant_id=tenant_id,
                actor_user_id=actor_user_id,
                entity_type="Department",
                entity_id=department.id,
                new_value={
                    "name": department.name,
                    "code": department.code,
                    "parent_department_id": (
                        str(department.parent_department_id)
                        if department.parent_department_id is not None
                        else None
                    ),
                },
            )
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise DepartmentConflictError from exc

        await self._session.refresh(department)
        return department

    async def list_roles(self, tenant_id: uuid.UUID) -> list[Role]:
        return await self._role_repository.list_visible_to_tenant(tenant_id)
