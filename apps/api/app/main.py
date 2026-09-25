from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.observability import RequestContextMiddleware


def create_application() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="GovControl API",
        version="0.1.0",
        openapi_url="/api/v1/openapi.json",
        docs_url="/api/v1/docs",
        redoc_url=None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "PUT"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(
        GZipMiddleware, minimum_size=settings.response_compression_minimum_size
    )
    app.add_middleware(RequestContextMiddleware, service_name="platform-api")
    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_application()
