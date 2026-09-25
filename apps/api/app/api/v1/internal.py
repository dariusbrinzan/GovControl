import uuid

from fastapi import APIRouter, HTTPException, status

from app.api.v1.auth import CurrentUserResponse
from app.core.security import (
    CurrentUserDependency,
    InternalServiceDependency,
    SessionDependency,
)
from app.services.platform import PlatformService

router = APIRouter(prefix="/internal", include_in_schema=False)


@router.get("/auth/context", response_model=CurrentUserResponse)
async def internal_auth_context(
    _: InternalServiceDependency, current_user: CurrentUserDependency
) -> CurrentUserResponse:
    """Resolve a forwarded user credential for an authenticated internal service."""
    return CurrentUserResponse(
        id=current_user.id,
        tenant_id=current_user.tenant_id,
        department_id=current_user.department_id,
        email=current_user.email,
        display_name=current_user.display_name,
        roles=sorted(current_user.roles),
        permissions=sorted(current_user.permissions),
    )


@router.get("/directory/assignments", status_code=status.HTTP_204_NO_CONTENT)
async def validate_directory_assignments(
    _: InternalServiceDependency,
    current_user: CurrentUserDependency,
    session: SessionDependency,
    department_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
) -> None:
    """Validate opaque organizational references inside the caller's tenant."""
    if not await PlatformService(session).assignments_exist(
        current_user.tenant_id, department_id, user_id
    ):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Department or user is unavailable in this tenant.",
        )
