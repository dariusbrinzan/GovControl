from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.security import AuthenticatedUser, SessionDependency, require_permission
from app.schemas.platform import (
    DepartmentCreate,
    DepartmentResponse,
    RoleResponse,
    TenantResponse,
)
from app.services.platform import (
    DepartmentConflictError,
    InvalidParentDepartmentError,
    PlatformService,
)

router = APIRouter(prefix="/platform")
PlatformManagerDependency = Annotated[
    AuthenticatedUser,
    Depends(require_permission("platform.manage")),
]


@router.get("/tenant", response_model=TenantResponse)
async def get_current_tenant(
    current_user: PlatformManagerDependency,
    session: SessionDependency,
) -> TenantResponse:
    """Get the caller's institution; the tenant is never selected by the client."""
    tenant = await PlatformService(session).get_tenant(current_user.tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant was not found.")
    return TenantResponse.model_validate(tenant)


@router.get("/departments", response_model=list[DepartmentResponse])
async def list_departments(
    current_user: PlatformManagerDependency,
    session: SessionDependency,
) -> list[DepartmentResponse]:
    """List departments belonging only to the authenticated user's tenant."""
    departments = await PlatformService(session).list_departments(current_user.tenant_id)
    return [DepartmentResponse.model_validate(department) for department in departments]


@router.post("/departments", response_model=DepartmentResponse, status_code=status.HTTP_201_CREATED)
async def create_department(
    department_data: DepartmentCreate,
    current_user: PlatformManagerDependency,
    session: SessionDependency,
) -> DepartmentResponse:
    """Create a department and its immutable creation audit event in one transaction."""
    try:
        department = await PlatformService(session).create_department(
            tenant_id=current_user.tenant_id,
            actor_user_id=current_user.id,
            department_data=department_data,
        )
    except InvalidParentDepartmentError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Parent department is not available within the current tenant.",
        ) from exc
    except DepartmentConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A department with this code already exists in the current tenant.",
        ) from exc
    return DepartmentResponse.model_validate(department)


@router.get("/roles", response_model=list[RoleResponse])
async def list_roles(
    current_user: PlatformManagerDependency,
    session: SessionDependency,
) -> list[RoleResponse]:
    """List system roles and tenant-defined roles visible to the caller's tenant."""
    roles = await PlatformService(session).list_roles(current_user.tenant_id)
    return [RoleResponse.model_validate(role) for role in roles]
