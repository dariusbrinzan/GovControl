import re
from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx
from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse

from gateway_app.assertions import issue_identity_assertion
from gateway_app.auth import require_csrf, resolve_session
from gateway_app.config import get_settings
from gateway_app.observability import current_request_id
from gateway_app.sessions import SessionStore

router = APIRouter(prefix="/api/v1", tags=["gateway"])

MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
FORWARDED_REQUEST_HEADERS = frozenset(
    {"accept", "content-type", "idempotency-key", "if-match", "if-none-match", "range"}
)
FORWARDED_RESPONSE_HEADERS = frozenset(
    {
        "accept-ranges",
        "content-disposition",
        "content-range",
        "content-type",
        "etag",
        "x-content-sha256",
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
            "legal": frozenset({"GET", "POST", "PATCH"}),
            "platform": frozenset({"GET", "POST", "PUT"}),
            "search": frozenset({"GET"}),
        },
    ),
    "govcontracts": UpstreamPolicy(
        base_url_setting="contracts_api_url",
        roots={"contracts": frozenset({"GET", "POST", "PATCH"})},
    ),
    "documents": UpstreamPolicy(
        base_url_setting="documents_api_url",
        roots={"documents": frozenset({"GET", "POST", "PATCH", "DELETE"})},
    ),
    "notifications": UpstreamPolicy(
        base_url_setting="notifications_api_url",
        roots={"notifications": frozenset({"GET", "POST", "PUT", "PATCH"})},
    ),
}

NOTIFICATION_ROUTE_METHODS = {
    "notifications": frozenset({"GET"}),
    "notifications/unread-count": frozenset({"GET"}),
    "notifications/preferences": frozenset({"GET", "PUT"}),
    "notifications/templates": frozenset({"GET", "POST"}),
    "notifications/audit": frozenset({"GET"}),
    "notifications/deliveries": frozenset({"GET"}),
    "notifications/mark-all-read": frozenset({"POST"}),
}
NOTIFICATION_ITEM_ROUTE = re.compile(
    r"^notifications/[0-9a-fA-F-]{36}/(read|unread|archive|restore)$"
)
NOTIFICATION_RETRY_ROUTE = re.compile(
    r"^notifications/deliveries/[0-9a-fA-F-]{36}/retry$"
)


def _validate_route(service: str, path: str, method: str) -> UpstreamPolicy:
    policy = POLICIES.get(service)
    if policy is None or not path:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Gateway route is not registered.")
    if "\\" in path or "\x00" in path or any(part in {"", ".", ".."} for part in path.split("/")):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Gateway route is not registered.")
    if service == "notifications":
        methods = NOTIFICATION_ROUTE_METHODS.get(path)
        if methods is None:
            if NOTIFICATION_ITEM_ROUTE.fullmatch(path):
                methods = frozenset({"PATCH"})
            elif NOTIFICATION_RETRY_ROUTE.fullmatch(path):
                methods = frozenset({"POST"})
        if methods is None or method not in methods:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Gateway route is not registered.")
    if service == "govcontracts" and path.startswith("contracts/notifications"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Gateway route is not registered.")
    root = path.split("/", 1)[0]
    methods = policy.roots.get(root)
    if methods is None or method not in methods:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Gateway route is not registered.")
    return policy


@router.api_route(
    "/documents",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    include_in_schema=False,
)
async def documents_root(request: Request) -> Response:
    return await proxy_request("documents", "documents", request)


@router.api_route(
    "/documents/{document_path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    include_in_schema=False,
)
async def documents_proxy(document_path: str, request: Request) -> Response:
    return await proxy_request("documents", f"documents/{document_path}", request)


@router.api_route(
    "/notifications",
    methods=["GET", "POST", "PUT", "PATCH"],
    include_in_schema=False,
)
async def notifications_root(request: Request) -> Response:
    return await proxy_request("notifications", "notifications", request)


@router.api_route(
    "/notifications/{notification_path:path}",
    methods=["GET", "POST", "PUT", "PATCH"],
    include_in_schema=False,
)
async def notifications_proxy(notification_path: str, request: Request) -> Response:
    return await proxy_request(
        "notifications", f"notifications/{notification_path}", request
    )


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

    if service == "documents" and request.method in MUTATING_METHODS:
        body_limit = settings.max_document_upload_bytes
    elif service == "notifications":
        body_limit = settings.max_notification_payload_bytes
    else:
        body_limit = settings.max_request_body_bytes

    async def limited_body() -> AsyncIterator[bytes]:
        received = 0
        async for chunk in request.stream():
            received += len(chunk)
            if received > body_limit:
                raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Request body is too large.")
            yield chunk

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
        upstream_request = request.app.state.http_client.build_request(
            request.method, target_url, headers=headers, content=limited_body()
        )
        if service == "documents":
            upstream_request.extensions["timeout"] = httpx.Timeout(
                settings.document_request_timeout_seconds,
                connect=settings.connect_timeout_seconds,
            ).as_dict()
        elif service == "notifications":
            upstream_request.extensions["timeout"] = httpx.Timeout(
                settings.notification_request_timeout_seconds,
                connect=settings.connect_timeout_seconds,
            ).as_dict()
        upstream = await request.app.state.http_client.send(upstream_request, stream=True)
    except HTTPException:
        raise
    except httpx.HTTPError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "The requested GovControl service is unavailable.",
        ) from exc

    async def upstream_body() -> AsyncIterator[bytes]:
        try:
            if upstream.is_stream_consumed:
                yield upstream.content
            else:
                async for chunk in upstream.aiter_bytes():
                    yield chunk
        finally:
            await upstream.aclose()

    response = StreamingResponse(
        content=upstream_body(),
        status_code=upstream.status_code,
        headers={
            name: value
            for name, value in upstream.headers.items()
            if name.lower() in FORWARDED_RESPONSE_HEADERS and name.lower() != "content-length"
        },
    )
    if rotated:
        SessionStore(request.app.state.redis, settings).set_cookie(response, session)
    return response
