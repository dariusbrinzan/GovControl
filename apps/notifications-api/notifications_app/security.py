import secrets
import uuid
from collections.abc import Awaitable, Callable
from typing import Annotated

import httpx
import jwt
from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from notifications_app.config import Settings, get_settings
from notifications_app.observability import current_request_id
from notifications_app.schemas import UserContext

bearer = HTTPBearer(auto_error=False)
Credentials = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]


def _assertion_ids(
    credentials: HTTPAuthorizationCredentials | None, settings: Settings
) -> tuple[uuid.UUID, uuid.UUID]:
    if credentials is None or settings.gateway_assertion_secret is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication is required.")
    try:
        claims = jwt.decode(
            credentials.credentials,
            settings.gateway_assertion_secret.get_secret_value(),
            algorithms=["HS256"],
            audience=settings.gateway_assertion_audience,
            issuer=settings.gateway_assertion_issuer,
            options={"require": ["exp", "iat", "nbf", "iss", "aud", "sub", "tenant_id"]},
        )
        return uuid.UUID(claims["sub"]), uuid.UUID(claims["tenant_id"])
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication is required.") from exc


async def get_current_user(
    request: Request,
    credentials: Credentials,
    settings: Annotated[Settings, Depends(get_settings)],
) -> UserContext:
    asserted_user_id, asserted_tenant_id = _assertion_ids(credentials, settings)
    if credentials is None or settings.internal_service_token is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Identity is not configured.")
    headers = {
        "Authorization": f"Bearer {credentials.credentials}",
        "X-Service-Token": settings.internal_service_token.get_secret_value(),
    }
    if request_id := current_request_id():
        headers["X-Request-ID"] = str(request_id)
    try:
        response = await request.app.state.http_client.get(
            f"{settings.platform_api_url.rstrip('/')}/internal/auth/context", headers=headers
        )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Identity is unavailable."
        ) from exc
    if response.status_code == status.HTTP_401_UNAUTHORIZED:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication is required.")
    if response.status_code != status.HTTP_200_OK:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Identity could not be verified.")
    user = UserContext.model_validate(response.json())
    if user.id != asserted_user_id or user.tenant_id != asserted_tenant_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication is required.")
    return user


CurrentUser = Annotated[UserContext, Depends(get_current_user)]


def require_permission(permission: str) -> Callable[[UserContext], Awaitable[UserContext]]:
    async def dependency(user: CurrentUser) -> UserContext:
        if permission not in user.permissions:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Notification permission is required.")
        return user

    return dependency


async def require_internal_service(
    settings: Annotated[Settings, Depends(get_settings)],
    service_token: Annotated[str | None, Header(alias="X-Service-Token")] = None,
) -> None:
    configured = settings.internal_service_token
    if configured is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Service auth is not configured.")
    if service_token is None or not secrets.compare_digest(
        service_token, configured.get_secret_value()
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid service credentials.")
