from fastapi import APIRouter

from app.api.v1.audit import router as audit_router
from app.api.v1.auth import router as auth_router
from app.api.v1.documents import router as documents_router
from app.api.v1.health import router as health_router
from app.api.v1.legal import router as legal_router
from app.api.v1.platform import router as platform_router
from app.api.v1.search import router as search_router

api_router = APIRouter()
api_router.include_router(auth_router, tags=["authentication"])
api_router.include_router(audit_router, tags=["audit"])
api_router.include_router(documents_router, tags=["documents"])
api_router.include_router(health_router, tags=["operations"])
api_router.include_router(platform_router, tags=["platform"])
api_router.include_router(legal_router, tags=["legal"])
api_router.include_router(search_router, tags=["search"])
