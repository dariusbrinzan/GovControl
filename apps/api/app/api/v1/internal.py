import uuid

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr, Field

from app.api.v1.auth import CurrentUserResponse
from app.core.security import (
    CurrentUserDependency,
    InternalServiceDependency,
    SessionDependency,
    SettingsDependency,
    build_user_context,
)
from app.services.identity import FederatedIdentityUnavailableError, IdentityService
from app.services.platform import PlatformService

router = APIRouter(prefix="/internal", include_in_schema=False)


class FederatedIdentityRequest(BaseModel):
    issuer: str = Field(min_length=1, max_length=2048)
    subject: str = Field(min_length=1, max_length=255)
    email: EmailStr
    email_verified: bool
    display_name: str | None = Field(None, max_length=255)


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


@router.post("/auth/oidc-context", response_model=CurrentUserResponse)
async def internal_oidc_context(
    identity: FederatedIdentityRequest,
    _: InternalServiceDependency,
    settings: SettingsDependency,
    session: SessionDependency,
) -> CurrentUserResponse:
    """Map a gateway-validated OIDC subject to an active tenant user."""
    issuer = identity.issuer.rstrip("/")
    if issuer not in settings.trusted_oidc_issuers:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "OIDC issuer is not trusted.")
    try:
        user = await IdentityService(session).resolve_federated_user(
            issuer=issuer,
            subject=identity.subject,
            email=str(identity.email),
            email_verified=identity.email_verified,
            allow_email_linking=settings.federated_email_linking_enabled,
        )
    except FederatedIdentityUnavailableError as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Federated identity is not provisioned."
        ) from exc
    context = await build_user_context(session, user)
    return CurrentUserResponse(
        id=context.id,
        tenant_id=context.tenant_id,
        department_id=context.department_id,
        email=context.email,
        display_name=context.display_name,
        roles=sorted(context.roles),
        permissions=sorted(context.permissions),
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
