from collections.abc import Awaitable, Callable
from typing import Annotated

import httpx
from fastapi import Depends, Header, HTTPException, status

from contracts_app.config import get_settings
from contracts_app.schemas import UserContext


async def get_current_user(authorization: Annotated[str | None, Header()] = None) -> UserContext:
    if authorization is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication is required.")
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=settings.platform_request_timeout_seconds) as client:
            response = await client.get(
                f"{settings.platform_api_url.rstrip('/')}/auth/me",
                headers={"Authorization": authorization},
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


CurrentUser = Annotated[UserContext, Depends(get_current_user)]


def require_permission(permission: str) -> Callable[[UserContext], Awaitable[UserContext]]:
    async def permission_dependency(user: CurrentUser) -> UserContext:
        if permission not in user.permissions:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "GovContracts access is required.")
        return user

    return permission_dependency


ContractManager = Annotated[UserContext, Depends(require_permission("contracts.manage"))]
ContractReporter = Annotated[UserContext, Depends(require_permission("contracts.report"))]
