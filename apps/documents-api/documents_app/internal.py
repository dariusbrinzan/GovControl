import uuid

from fastapi import APIRouter, Depends

from documents_app.export_insights import snapshot as insights_snapshot
from documents_app.security import require_internal_service

router = APIRouter(
    prefix="/internal",
    dependencies=[Depends(require_internal_service)],
    include_in_schema=False,
)


@router.get("/insights/snapshot/{tenant_id}")
async def export_insights_snapshot(tenant_id: uuid.UUID) -> dict[str, object]:
    return await insights_snapshot(tenant_id)
