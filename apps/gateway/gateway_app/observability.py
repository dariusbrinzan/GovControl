import json
import logging
import time
import uuid
from contextvars import ContextVar

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

request_id_context: ContextVar[uuid.UUID | None] = ContextVar("request_id", default=None)
logger = logging.getLogger("uvicorn.error")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Correlate requests without ever recording credentials or cookies."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        raw_request_id = request.headers.get("X-Request-ID")
        try:
            request_id = uuid.UUID(raw_request_id) if raw_request_id else uuid.uuid4()
        except ValueError:
            request_id = uuid.uuid4()
        token = request_id_context.set(request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            request_id_context.reset(token)
        response.headers["X-Request-ID"] = str(request_id)
        logger.info(
            json.dumps(
                {
                    "event": "http_request",
                    "service": "gateway",
                    "request_id": str(request_id),
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                }
            )
        )
        return response


def current_request_id() -> uuid.UUID | None:
    return request_id_context.get()
