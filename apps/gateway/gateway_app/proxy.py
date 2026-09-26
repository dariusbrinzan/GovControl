from dataclasses import dataclass

import httpx
from fastapi import APIRouter, HTTPException, Request, Response, status

from gateway_app.assertions import issue_identity_assertion
from gateway_app.auth import require_csrf, resolve_session
from gateway_app.config import get_settings
from gateway_app.observability import current_request_id
from gateway_app.sessions import SessionStore

router = APIRouter(prefix="/api/v1", tags=["gateway"])

MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
FORWARDED_REQUEST_HEADERS = frozenset(
    {"accept", "content-type", "if-match", "if-none-match", "range"}
)
FORWARDED_RESPONSE_HEADERS = frozenset(
    {
        "accept-ranges",
        "content-disposition",
        "content-range",
        "content-type",
        "etag",
    }
)


@dataclass(frozen=True)
class UpstreamPolicy:
    base_url_setting: str
    roots: dict[str, frozenset[str]]


POLICIES = {
    "platform": UpstreamPolicy(
        base_url_setting="platform_api_url",
        roots={
            "analytics": frozenset({"GET"}),
            "audit": frozenset({"GET"}),
            "documents": frozenset({"GET", "POST"}),
            "legal": frozenset({"GET", "POST", "PATCH"}),
            "notifications": frozenset({"GET", "PATCH"}),
            "platform": frozenset({"GET", "POST", "PUT"}),
            "search": frozenset({"GET"}),
        },
    ),
    "govcontracts": UpstreamPolicy(
        base_url_setting="contracts_api_url",
        roots={"contracts": frozenset({"GET", "POST", "PATCH"})},
    ),
}


def _validate_route(service: str, path: str, method: str) -> UpstreamPolicy:
    policy = POLICIES.get(service)
    if policy is None or not path:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Gateway route is not registered.")
    if "\\" in path or "\x00" in path or any(part in {"", ".", ".."} for part in path.split("/")):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Gateway route is not registered.")
    root = path.split("/", 1)[0]
    methods = policy.roots.get(root)
    if methods is None or method not in methods:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Gateway route is not registered.")
    return policy


@router.api_route(
    "/{service}/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    include_in_schema=False,
)
async def proxy_request(service: str, path: str, request: Request) -> Response:
    settings = get_settings()
    policy = _validate_route(service, path, request.method)
    session, rotated = await resolve_session(
        request,
        settings,
        request.cookies.get(settings.session_cookie_name),
    )
    if request.method in MUTATING_METHODS:
        require_csrf(session, request.headers.get("X-CSRF-Token"))

    body = await request.body()
    if len(body) > settings.max_request_body_bytes:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Request body is too large.")

    base_url = getattr(settings, policy.base_url_setting).rstrip("/")
    target_url = f"{base_url}/{path}"
    if request.url.query:
        target_url = f"{target_url}?{request.url.query}"
    headers = {
        name: value
        for name, value in request.headers.items()
        if name.lower() in FORWARDED_REQUEST_HEADERS
    }
    headers["Authorization"] = f"Bearer {issue_identity_assertion(session, settings)}"
    request_id = current_request_id()
    if request_id is not None:
        headers["X-Request-ID"] = str(request_id)
    try:
        upstream = await request.app.state.http_client.request(
            request.method,
            target_url,
            headers=headers,
            content=body,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "The requested GovControl service is unavailable.",
        ) from exc

    response = Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers={
            name: value
            for name, value in upstream.headers.items()
            if name.lower() in FORWARDED_RESPONSE_HEADERS
        },
    )
    if rotated:
        SessionStore(request.app.state.redis, settings).set_cookie(response, session)
    return response
