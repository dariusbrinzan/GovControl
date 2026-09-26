import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

import httpx
import redis.asyncio as redis
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from gateway_app.auth import router as auth_router
from gateway_app.config import get_settings
from gateway_app.middleware import RequestGuardMiddleware, SecurityHeadersMiddleware
from gateway_app.observability import RequestContextMiddleware
from gateway_app.oidc import OIDCClient
from gateway_app.proxy import router as proxy_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    timeout = httpx.Timeout(
        settings.request_timeout_seconds,
        connect=settings.connect_timeout_seconds,
    )
    app.state.http_client = httpx.AsyncClient(timeout=timeout, follow_redirects=False)
    app.state.redis = redis.from_url(settings.redis_url, decode_responses=True)
    app.state.oidc_client = OIDCClient(app.state.http_client, app.state.redis, settings)
    try:
        yield
    finally:
        await app.state.http_client.aclose()
        await app.state.redis.aclose()


def create_application() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="GovControl Gateway",
        version="0.1.0",
        docs_url="/docs" if settings.app_env != "production" else None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
        allow_headers=[
            "Content-Type",
            "Idempotency-Key",
            "If-Match",
            "If-None-Match",
            "Range",
            "X-CSRF-Token",
            "X-Request-ID",
        ],
        expose_headers=[
            "Content-Disposition",
            "Content-Range",
            "ETag",
            "Retry-After",
            "X-Content-SHA256",
            "X-Request-ID",
        ],
    )
    app.add_middleware(RequestGuardMiddleware, settings=settings)
    app.add_middleware(SecurityHeadersMiddleware, settings=settings)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(auth_router)
    app.include_router(proxy_router)

    @app.get("/health")
    async def health() -> dict[Literal["status", "service"], str]:
        return {"status": "ok", "service": "gateway"}

    @app.get("/ready")
    async def ready() -> dict[Literal["status"], Literal["ready"]]:
        try:
            await app.state.redis.ping()
            platform, contracts, documents, notifications = await asyncio.gather(
                app.state.http_client.get(f"{settings.platform_api_url.rstrip('/')}/health"),
                app.state.http_client.get(f"{settings.contracts_api_url.removesuffix('/api/v1')}/health"),
                app.state.http_client.get(f"{settings.documents_api_url.removesuffix('/api/v1')}/health"),
                app.state.http_client.get(
                    f"{settings.notifications_api_url.removesuffix('/api/v1')}/health"
                ),
            )
            platform.raise_for_status()
            contracts.raise_for_status()
            documents.raise_for_status()
            notifications.raise_for_status()
        except (httpx.HTTPError, redis.RedisError) as exc:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "A gateway dependency is unavailable.",
            ) from exc
        return {"status": "ready"}

    return app


app = create_application()
