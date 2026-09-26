import secrets

import httpx
from fastapi import APIRouter, Header, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse

from gateway_app.audit import record_auth_event
from gateway_app.config import Settings, get_settings
from gateway_app.models import SessionRecord, SessionResponse, UserContext
from gateway_app.observability import current_request_id
from gateway_app.oidc import OIDCError
from gateway_app.sessions import SessionStore

router = APIRouter(prefix="/auth", tags=["authentication"])


def _store(request: Request, settings: Settings) -> SessionStore:
    return SessionStore(request.app.state.redis, settings)


async def resolve_session(
    request: Request,
    settings: Settings,
    cookie: str | None,
) -> tuple[SessionRecord, bool]:
    store = _store(request, settings)
    record = await store.resolve(cookie)
    if record is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication is required.")
    rotated = store.rotation_due(record)
    if rotated:
        record = await store.rotate(record)
        await record_auth_event(
            request.app.state.redis, "session.rotated", outcome="success", session=record
        )
    return record, rotated


def require_csrf(record: SessionRecord, csrf_token: str | None) -> None:
    if csrf_token is None or not secrets.compare_digest(record.csrf_token, csrf_token):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "A valid CSRF token is required.")


@router.get("/config")
async def auth_config() -> dict[str, str]:
    settings = get_settings()
    return {"mode": settings.auth_mode, "login_url": "/auth/login"}


@router.get("/login", response_class=RedirectResponse)
async def oidc_login(request: Request) -> RedirectResponse:
    settings = get_settings()
    if settings.auth_mode != "oidc":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "OIDC login is unavailable.")
    try:
        location = await request.app.state.oidc_client.begin()
    except OIDCError as exc:
        await record_auth_event(
            request.app.state.redis, "login.oidc.started", outcome="failure"
        )
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    await record_auth_event(request.app.state.redis, "login.oidc.started", outcome="success")
    return RedirectResponse(location, status_code=status.HTTP_302_FOUND)


@router.get("/callback", response_class=RedirectResponse)
async def oidc_callback(
    request: Request,
    state: str,
    code: str,
) -> RedirectResponse:
    settings = get_settings()
    if settings.auth_mode != "oidc":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "OIDC login is unavailable.")
    try:
        identity = await request.app.state.oidc_client.complete(state=state, code=code)
    except OIDCError as exc:
        await record_auth_event(
            request.app.state.redis, "login.oidc.completed", outcome="failure"
        )
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
    if settings.internal_service_token is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Service authentication is not configured."
        )
    headers = {"X-Service-Token": settings.internal_service_token.get_secret_value()}
    request_id = current_request_id()
    if request_id is not None:
        headers["X-Request-ID"] = str(request_id)
    try:
        upstream = await request.app.state.http_client.post(
            f"{settings.platform_api_url.rstrip('/')}/internal/auth/oidc-context",
            headers=headers,
            json=identity.model_dump(mode="json"),
        )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Identity service is unavailable."
        ) from exc
    if upstream.status_code != status.HTTP_200_OK:
        await record_auth_event(
            request.app.state.redis, "login.oidc.completed", outcome="failure",
            detail="identity_not_provisioned"
        )
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Identity is not provisioned.")
    user = UserContext.model_validate(upstream.json())
    store = _store(request, settings)
    record = await store.create(
        user,
        "oidc",
        oidc_issuer=identity.issuer,
        oidc_subject=identity.subject,
    )
    response = RedirectResponse(settings.portal_after_login_url, status_code=status.HTTP_302_FOUND)
    store.set_cookie(response, record)
    await record_auth_event(
        request.app.state.redis, "login.oidc.completed", outcome="success", session=record
    )
    return response


@router.post("/local/login", response_model=SessionResponse)
async def local_login(request: Request, response: Response) -> SessionResponse:
    settings = get_settings()
    if settings.app_env != "development" or settings.auth_mode != "local":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Local login is unavailable.")
    if settings.dev_auth_token is None or settings.internal_service_token is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Local authentication is not configured."
        )
    headers = {
        "Authorization": f"Bearer {settings.dev_auth_token.get_secret_value()}",
        "X-Service-Token": settings.internal_service_token.get_secret_value(),
    }
    request_id = current_request_id()
    if request_id is not None:
        headers["X-Request-ID"] = str(request_id)
    try:
        upstream = await request.app.state.http_client.get(
            f"{settings.platform_api_url.rstrip('/')}/internal/auth/context",
            headers=headers,
        )
    except httpx.HTTPError as exc:
        await record_auth_event(
            request.app.state.redis, "login.local", outcome="failure", detail="platform_unavailable"
        )
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Identity service is unavailable."
        ) from exc
    if upstream.status_code != status.HTTP_200_OK:
        await record_auth_event(
            request.app.state.redis, "login.local", outcome="failure", detail="identity_rejected"
        )
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Local identity was rejected.")
    user = UserContext.model_validate(upstream.json())
    store = _store(request, settings)
    record = await store.create(user, "local")
    store.set_cookie(response, record)
    await record_auth_event(
        request.app.state.redis, "login.local", outcome="success", session=record
    )
    return SessionResponse(
        user=record.user,
        csrf_token=record.csrf_token,
        expires_at=record.expires_at,
        auth_method=record.auth_method,
    )


@router.get("/session", response_model=SessionResponse)
async def get_session(
    request: Request,
    response: Response,
) -> SessionResponse:
    settings = get_settings()
    cookie = request.cookies.get(settings.session_cookie_name)
    record, rotated = await resolve_session(request, settings, cookie)
    if rotated:
        _store(request, settings).set_cookie(response, record)
    return SessionResponse(
        user=record.user,
        csrf_token=record.csrf_token,
        expires_at=record.expires_at,
        auth_method=record.auth_method,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    csrf_token: str | None = Header(None, alias="X-CSRF-Token"),
) -> None:
    settings = get_settings()
    store = _store(request, settings)
    record = await store.resolve(request.cookies.get(settings.session_cookie_name))
    if record is None:
        store.clear_cookie(response)
        return
    require_csrf(record, csrf_token)
    await store.destroy(record.id)
    store.clear_cookie(response)
    await record_auth_event(request.app.state.redis, "logout", outcome="success", session=record)
