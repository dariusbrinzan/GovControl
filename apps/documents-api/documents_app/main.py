import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Literal

import httpx
import redis.asyncio as redis
from fastapi import FastAPI, HTTPException, status
from sqlalchemy import text
from starlette.concurrency import run_in_threadpool

from documents_app.api import router
from documents_app.config import get_settings
from documents_app.database import session_factory
from documents_app.observability import RequestContextMiddleware
from documents_app.storage import S3Storage


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    app.state.http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(settings.dependency_timeout_seconds, connect=3.0),
        follow_redirects=False,
        limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
    )
    app.state.redis = redis.from_url(settings.redis_url, decode_responses=True)
    app.state.storage = S3Storage(settings)
    try:
        yield
    finally:
        await app.state.http_client.aclose()
        await app.state.redis.aclose()


def create_application() -> FastAPI:
    app = FastAPI(
        title="GovDocuments API",
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
        return {"status": "ok", "service": "govdocuments"}

    @app.get("/ready")
    async def ready() -> dict[str, Any]:
        settings = get_settings()

        async def database_check() -> None:
            async with session_factory() as session:
                await session.execute(text("SELECT 1"))

        async def storage_check() -> None:
            await run_in_threadpool(app.state.storage.check)

        async def redis_check() -> None:
            await app.state.redis.ping()

        async def http_check(url: str) -> None:
            response = await app.state.http_client.get(url)
            response.raise_for_status()

        platform_root = settings.platform_api_url.rstrip("/").removesuffix("/api/v1")
        contracts_root = settings.contracts_api_url.rstrip("/").removesuffix("/api/v1")
        checks = {
            "database": database_check(),
            "object_storage": storage_check(),
            "redis": redis_check(),
            "platform": http_check(f"{platform_root}/api/v1/health"),
            "contracts": http_check(f"{contracts_root}/health"),
        }
        results = await asyncio.gather(*checks.values(), return_exceptions=True)
        components = {
            name: "ready" if not isinstance(result, Exception) else "unavailable"
            for name, result in zip(checks, results, strict=True)
        }
        if any(value != "ready" for value in components.values()):
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                {"status": "unavailable", "components": components},
            )
        return {"status": "ready", "components": components}

    return app


app = create_application()
