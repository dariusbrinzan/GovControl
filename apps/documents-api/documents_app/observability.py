import contextvars
import json
import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

request_id_context: contextvars.ContextVar[uuid.UUID | None] = contextvars.ContextVar(
    "request_id", default=None
)
logger = logging.getLogger("govdocuments.access")


def request_id_from_header(value: str | None) -> uuid.UUID:
    try:
        return uuid.UUID(value) if value else uuid.uuid4()
    except ValueError:
        return uuid.uuid4()


def current_request_id() -> uuid.UUID | None:
    return request_id_context.get()


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request_id_from_header(request.headers.get("X-Request-ID"))
        token = request_id_context.set(request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = str(request_id)
            logger.info(
                json.dumps(
                    {
                        "event": "http_request",
                        "service": "govdocuments-api",
                        "method": request.method,
                        "path": request.url.path,
                        "status": response.status_code,
                        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                        "request_id": str(request_id),
                    },
                    separators=(",", ":"),
                )
            )
            return response
        finally:
            request_id_context.reset(token)
