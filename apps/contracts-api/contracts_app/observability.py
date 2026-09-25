import json
import logging
import time
import uuid
from contextvars import ContextVar

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

request_id_context: ContextVar[uuid.UUID | None] = ContextVar("request_id", default=None)
logger = logging.getLogger("govcontracts.http")


def current_request_id() -> uuid.UUID | None:
    return request_id_context.get()


def request_id_from_header(value: str | None) -> uuid.UUID:
    if value is not None:
        try:
            return uuid.UUID(value)
        except ValueError:
            pass
    return uuid.uuid4()


class RequestContextMiddleware:
    """Attach a correlation ID and emit one structured access log per HTTP request."""

    def __init__(self, app: ASGIApp, service_name: str) -> None:
        self.app = app
        self.service_name = service_name

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = request_id_from_header(Headers(scope=scope).get("X-Request-ID"))
        context_token = request_id_context.set(request_id)
        started_at = time.perf_counter()
        status_code = 500

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                MutableHeaders(scope=message)["X-Request-ID"] = str(request_id)
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
            logger.info(
                json.dumps(
                    {
                        "event": "http_request",
                        "service": self.service_name,
                        "request_id": str(request_id),
                        "method": scope.get("method"),
                        "path": scope.get("path"),
                        "status_code": status_code,
                        "duration_ms": duration_ms,
                    },
                    separators=(",", ":"),
                )
            )
            request_id_context.reset(context_token)
