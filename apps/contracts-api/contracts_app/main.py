from typing import Literal

import httpx
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from contracts_app.api import router
from contracts_app.config import get_settings
from contracts_app.database import session_factory
from contracts_app.internal import router as internal_router
from contracts_app.observability import RequestContextMiddleware
from contracts_app.observability import current_request_id


def create_application() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="GovContracts API",
        version="0.1.0",
        openapi_url="/api/v1/openapi.json",
        docs_url="/api/v1/docs",
        redoc_url=None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(RequestContextMiddleware, service_name="govcontracts-api")

    @app.get("/health")
    async def health() -> dict[Literal["status", "service"], str]:
        return {"status": "ok", "service": "govcontracts"}

    @app.get("/ready")
    async def ready() -> dict[Literal["status"], Literal["ready"]]:
        try:
            async with session_factory() as session:
                await session.execute(text("SELECT 1"))
        except SQLAlchemyError as exc:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, "Database is unavailable."
            ) from exc
        headers: dict[str, str] = {}
        request_id = current_request_id()
        if request_id is not None:
            headers["X-Request-ID"] = str(request_id)
        try:
            async with httpx.AsyncClient(
                timeout=settings.platform_request_timeout_seconds
            ) as client:
                response = await client.get(
                    f"{settings.platform_api_url.rstrip('/')}/health", headers=headers
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, "Identity service is unavailable."
            ) from exc
        return {"status": "ready"}

    app.include_router(router, prefix="/api/v1")
    app.include_router(internal_router, prefix="/api/v1")
    return app


app = create_application()
