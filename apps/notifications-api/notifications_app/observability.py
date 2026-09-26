import contextvars
import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

_request_id: contextvars.ContextVar[uuid.UUID | None] = contextvars.ContextVar(
    "notifications_request_id", default=None
)


def current_request_id() -> uuid.UUID | None:
    return _request_id.get()


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        try:
            request_id = uuid.UUID(request.headers.get("X-Request-ID", ""))
        except ValueError:
            request_id = uuid.uuid4()
        token = _request_id.set(request_id)
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = str(request_id)
            return response
        finally:
            _request_id.reset(token)
