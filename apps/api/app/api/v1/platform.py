import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.security import (
    AuthenticatedUser,
    SessionDependency,
    require_any_permission,
    require_permission,
)
from app.schemas.platform import (
    DepartmentCreate,
    DepartmentResponse,
    InstitutionDirectoryResponse,
    RoleResponse,
    TenantResponse,
    UserCreate,
    UserResponse,
    UserRoleAssign,
)
from app.services.platform import (
    DepartmentConflictError,
    InvalidParentDepartmentError,
    PlatformService,
    ResourceNotFoundError,
    UserConflictError,
)

router = APIRouter(prefix="/platform")
PlatformManagerDependency = Annotated[
    AuthenticatedUser,
    Depends(require_permission("platform.manage")),
]
DirectoryReaderDependency = Annotated[
    AuthenticatedUser,
    Depends(
        require_any_permission("platform.manage", "legal.manage", "contracts.manage")
    ),
]


@router.get("/directory", response_model=InstitutionDirectoryResponse)
async def institution_directory(
    current_user: DirectoryReaderDependency,
    session: SessionDependency,
) -> InstitutionDirectoryResponse:
    """Return tenant-scoped department and active-user labels for assignment controls."""
    service = PlatformService(session)
    departments = await service.list_departments(current_user.tenant_id)
    users = await service.list_users(current_user.tenant_id)
    return InstitutionDirectoryResponse(
        departments=[DepartmentResponse.model_validate(item) for item in departments],
        users=[UserResponse.model_validate(item) for item in users if item.is_active],
    )


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


@router.get("/users", response_model=list[UserResponse])
async def list_users(
    current_user: PlatformManagerDependency,
    session: SessionDependency,
) -> list[UserResponse]:
    """List only users that belong to the authenticated user's tenant."""
    users = await PlatformService(session).list_users(current_user.tenant_id)
    return [UserResponse.model_validate(user) for user in users]


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_data: UserCreate,
    current_user: PlatformManagerDependency,
    session: SessionDependency,
) -> UserResponse:
    """Create a tenant user identity without creating a local password."""
    try:
        user = await PlatformService(session).create_user(
            tenant_id=current_user.tenant_id,
            actor_user_id=current_user.id,
            user_data=user_data,
        )
    except ResourceNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Department is not available within the current tenant.",
        ) from exc
    except UserConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists in the current tenant.",
        ) from exc
    return UserResponse.model_validate(user)


@router.put("/users/{user_id}/roles", status_code=status.HTTP_204_NO_CONTENT)
async def assign_role_to_user(
    user_id: uuid.UUID,
    assignment: UserRoleAssign,
    current_user: PlatformManagerDependency,
    session: SessionDependency,
) -> None:
    """Assign a system or current-tenant role to a user, idempotently."""
    try:
        await PlatformService(session).assign_role_to_user(
            tenant_id=current_user.tenant_id,
            actor_user_id=current_user.id,
            user_id=user_id,
            role_id=assignment.role_id,
        )
    except ResourceNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User or role was not found in the current tenant context.",
        ) from exc
