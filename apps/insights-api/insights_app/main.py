import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import httpx
import redis.asyncio as redis
from fastapi import FastAPI, HTTPException, status
from sqlalchemy import text

from insights_app.api import router
from insights_app.config import get_settings
from insights_app.database import session_factory
from insights_app.models import ProjectionCheckpoint
from insights_app.observability import RequestContextMiddleware
from insights_app.storage import create_storage


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    app.state.http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(settings.dependency_timeout_seconds, connect=3.0),
        follow_redirects=False,
        limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
    )
    app.state.redis = redis.from_url(settings.redis_url, decode_responses=True)
    app.state.export_storage = create_storage(settings)
    try:
        yield
    finally:
        await app.state.http_client.aclose()
        await app.state.redis.aclose()


def create_application() -> FastAPI:
    app = FastAPI(
        title="GovInsights API",
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
        return {"status": "ok", "service": "govinsights"}

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

        async def storage_check() -> None:
            await app.state.export_storage.ready()

        checks = {
            "database": database_check(),
            "redis": redis_check(),
            "platform_identity": identity_check(),
            "object_storage": storage_check(),
        }
        results = await asyncio.gather(*checks.values(), return_exceptions=True)
        components = {
            name: "ready" if not isinstance(result, Exception) else "unavailable"
            for name, result in zip(checks, results, strict=True)
        }
        async with session_factory() as session:
            try:
                checkpoint = await session.get(ProjectionCheckpoint, settings.consumer_group)
                fresh = (
                    checkpoint is not None
                    and checkpoint.last_processed_at is not None
                    and checkpoint.last_processed_at
                    >= datetime.now(UTC) - timedelta(seconds=settings.projection_stale_seconds)
                )
                components["consumer"] = "ready" if checkpoint else "starting"
                components["projection_freshness"] = "ready" if fresh else "stale"
            except Exception:
                components["consumer"] = "unavailable"
                components["projection_freshness"] = "unavailable"
        unavailable = {"database", "redis", "platform_identity", "object_storage"}
        if any(components[name] != "ready" for name in unavailable):
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                {"status": "unavailable", "components": components},
            )
        return {"status": "ready", "components": components}

    return app


app = create_application()
