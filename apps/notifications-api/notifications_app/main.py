import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Literal

import httpx
import redis.asyncio as redis
from fastapi import FastAPI, HTTPException, status
from sqlalchemy import text

from notifications_app.api import router
from notifications_app.config import get_settings
from notifications_app.database import session_factory
from notifications_app.observability import RequestContextMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    app.state.http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(settings.dependency_timeout_seconds, connect=3.0),
        follow_redirects=False,
        limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
    )
    app.state.redis = redis.from_url(settings.redis_url, decode_responses=True)
    try:
        yield
    finally:
        await app.state.http_client.aclose()
        await app.state.redis.aclose()


def create_application() -> FastAPI:
    app = FastAPI(
        title="GovNotifications API",
        version="0.1.0",
        openapi_url="/api/v1/openapi.json",
        docs_url="/api/v1/docs",
        redoc_url=None,
        lifespan=lifespan,
    )
    app.add_middleware(RequestContextMiddleware)
    app.include_router(router, prefix="/api/v1")

    @app.get("/health")
    async def health() -> dict[Literal["status", "service"], str]:
        return {"status": "ok", "service": "govnotifications"}

    @app.get("/ready")
    async def ready() -> dict[str, Any]:
        settings = get_settings()

        async def database_check() -> None:
            async with session_factory() as session:
                await session.execute(text("SELECT 1"))

        async def redis_check() -> None:
            await app.state.redis.ping()

        async def identity_check() -> None:
            response = await app.state.http_client.get(
                f"{settings.platform_api_url.rstrip('/')}/health"
            )
            response.raise_for_status()

        checks = {
            "database": database_check(),
            "redis": redis_check(),
            "platform_identity": identity_check(),
        }
        results = await asyncio.gather(*checks.values(), return_exceptions=True)
        components = {
            name: "ready" if not isinstance(result, Exception) else "unavailable"
            for name, result in zip(checks, results, strict=True)
        }
        components["in_app"] = "ready"
        email_ready = not settings.email_enabled or settings.smtp_host
        components["email"] = "ready" if email_ready else "unavailable"
        if any(value != "ready" for value in components.values()):
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                {"status": "unavailable", "components": components},
            )
        return {"status": "ready", "components": components}

    return app


app = create_application()
