from fastapi import APIRouter

from app.api.v1.auth import CurrentUserResponse
from app.core.security import CurrentUserDependency, InternalServiceDependency

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
