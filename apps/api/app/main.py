from fastapi import FastAPI

from app.api.v1.router import api_router


def create_application() -> FastAPI:
    app = FastAPI(
        title="GovControl API",
        version="0.1.0",
        openapi_url="/api/v1/openapi.json",
        docs_url="/api/v1/docs",
        redoc_url=None,
    )
    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_application()
