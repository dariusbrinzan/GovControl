import hashlib
import time

import redis.asyncio as redis
from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from gateway_app.config import Settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: object, settings: Settings):
        super().__init__(app)  # type: ignore[arg-type]
        self.production = settings.app_env == "production"

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        response.headers["Cache-Control"] = "no-store"
        if self.production:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


class RequestGuardMiddleware(BaseHTTPMiddleware):
    """Apply coarse abuse controls before authentication and proxy handling."""

    def __init__(self, app: object, settings: Settings):
        super().__init__(app)  # type: ignore[arg-type]
        self.settings = settings

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        document_mutation = request.url.path.startswith("/api/v1/documents") and (
            request.method in {"POST", "PUT", "PATCH"}
        )
        origin = request.headers.get("origin")
        if (
            request.method in {"POST", "PUT", "PATCH", "DELETE"}
            and origin is not None
            and origin not in self.settings.allowed_origins
        ):
            return JSONResponse(
                {"detail": "Request origin is not allowed."},
                status_code=status.HTTP_403_FORBIDDEN,
            )
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                body_limit = (
                    self.settings.max_document_upload_bytes
                    if document_mutation
                    else self.settings.max_request_body_bytes
                )
                if int(content_length) > body_limit:
                    return JSONResponse(
                        {"detail": "Request body is too large."},
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    )
            except ValueError:
                return JSONResponse(
                    {"detail": "Invalid Content-Length header."},
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
        if request.url.path in {"/health", "/ready"}:
            return await call_next(request)
        client = request.client.host if request.client else "unknown"
        cookie = request.cookies.get(self.settings.session_cookie_name, "anonymous")
        subject = hashlib.sha256(f"{client}:{cookie}".encode()).hexdigest()
        window = int(time.time()) // self.settings.rate_limit_window_seconds
        rate_scope = "document-upload" if document_mutation else "general"
        key = f"govcontrol:gateway:rate:{rate_scope}:{window}:{subject}"
        client_redis = request.app.state.redis
        try:
            count = await client_redis.incr(key)
            if count == 1:
                await client_redis.expire(key, self.settings.rate_limit_window_seconds + 1)
        except redis.RedisError:
            return JSONResponse(
                {"detail": "Gateway rate limiting is unavailable."},
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        limit = (
            self.settings.document_upload_rate_limit_requests
            if document_mutation
            else self.settings.rate_limit_requests
        )
        if count > limit:
            response = JSONResponse(
                {"detail": "Rate limit exceeded."},
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            )
            response.headers["Retry-After"] = str(self.settings.rate_limit_window_seconds)
            return response
        return await call_next(request)
