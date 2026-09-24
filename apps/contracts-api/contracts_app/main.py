from typing import Literal

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from contracts_app.api import router
from contracts_app.config import get_settings
from contracts_app.database import session_factory


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
        allow_headers=["Authorization", "Content-Type"],
    )

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
        return {"status": "ready"}

    app.include_router(router, prefix="/api/v1")
    return app


app = create_application()
