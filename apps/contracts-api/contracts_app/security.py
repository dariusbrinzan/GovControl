import secrets
from collections.abc import Awaitable, Callable
from typing import Annotated

import httpx
from fastapi import Depends, Header, HTTPException, status

from contracts_app.config import get_settings
from contracts_app.observability import current_request_id
from contracts_app.schemas import UserContext


async def get_current_user(authorization: Annotated[str | None, Header()] = None) -> UserContext:
    if authorization is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication is required.")
    settings = get_settings()
    headers = {"Authorization": authorization}
    auth_path = "/auth/me"
    if settings.internal_service_token is not None:
        auth_path = "/internal/auth/context"
        headers["X-Service-Token"] = settings.internal_service_token.get_secret_value()
    request_id = current_request_id()
    if request_id is not None:
        headers["X-Request-ID"] = str(request_id)
    try:
        async with httpx.AsyncClient(timeout=settings.platform_request_timeout_seconds) as client:
            response = await client.get(
                f"{settings.platform_api_url.rstrip('/')}{auth_path}",
                headers=headers,
            )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Identity service is unavailable."
        ) from exc
    if response.status_code == status.HTTP_401_UNAUTHORIZED:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication is required.")
    if response.status_code != status.HTTP_200_OK:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Identity could not be verified.")
    return UserContext.model_validate(response.json())


async def require_internal_service(
    service_token: Annotated[str | None, Header(alias="X-Service-Token")] = None,
) -> None:
    configured_token = get_settings().internal_service_token
    if configured_token is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Internal service authentication is not configured.",
        )
    if service_token is None or not secrets.compare_digest(
        service_token, configured_token.get_secret_value()
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid service credentials.")


CurrentUser = Annotated[UserContext, Depends(get_current_user)]


def require_permission(permission: str) -> Callable[[UserContext], Awaitable[UserContext]]:
    async def permission_dependency(user: CurrentUser) -> UserContext:
        if permission not in user.permissions:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "GovContracts access is required.")
        return user

    return permission_dependency


ContractManager = Annotated[UserContext, Depends(require_permission("contracts.manage"))]
ContractReporter = Annotated[UserContext, Depends(require_permission("contracts.report"))]
ContractAuditor = Annotated[UserContext, Depends(require_permission("audit.view"))]
InternalService = Annotated[None, Depends(require_internal_service)]
