import secrets
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.models.rbac import Permission, Role, RolePermission, UserRole
from app.models.tenant import Tenant
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthenticatedUser:
    """The tenant-bound identity established by the backend authentication layer."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    department_id: uuid.UUID | None
    email: str
    display_name: str
    roles: frozenset[str]
    permissions: frozenset[str]


SettingsDependency = Annotated[Settings, Depends(get_settings)]
SessionDependency = Annotated[AsyncSession, Depends(get_db_session)]
CredentialsDependency = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)]


async def get_current_user(
    settings: SettingsDependency,
    session: SessionDependency,
    credentials: CredentialsDependency,
) -> AuthenticatedUser:
    """Authenticate the configured local developer identity in development only."""
    configured_token = settings.dev_auth_token
    if (
        settings.app_env != "development"
        or not settings.dev_auth_enabled
        or configured_token is None
        or settings.dev_auth_email is None
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Development authentication is disabled.",
        )

    if (
        credentials is None
        or credentials.scheme.lower() != "bearer"
        or not secrets.compare_digest(credentials.credentials, configured_token.get_secret_value())
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await session.scalar(
        select(User)
        .join(Tenant, Tenant.id == User.tenant_id)
        .where(
            User.email == settings.dev_auth_email,
            User.is_active.is_(True),
            Tenant.is_active.is_(True),
        )
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authenticated development user is unavailable.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    permission_keys = await session.scalars(
        select(Permission.key)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .where(UserRole.user_id == user.id)
    )
    role_keys = await session.scalars(
        select(Role.key)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user.id)
    )
    return AuthenticatedUser(
        id=user.id,
        tenant_id=user.tenant_id,
        department_id=user.department_id,
        email=user.email,
        display_name=user.display_name,
        roles=frozenset(role_keys.all()),
        permissions=frozenset(permission_keys.all()),
    )


CurrentUserDependency = Annotated[AuthenticatedUser, Depends(get_current_user)]


def require_permission(
    permission: str,
) -> Callable[[AuthenticatedUser], Awaitable[AuthenticatedUser]]:
    """Create a dependency that rejects users lacking a required backend permission."""

    async def permission_dependency(current_user: CurrentUserDependency) -> AuthenticatedUser:
        if permission not in current_user.permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action.",
            )
        return current_user

    return permission_dependency
