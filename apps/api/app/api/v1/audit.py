from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.core.security import AuthenticatedUser, SessionDependency, require_permission
from app.models.audit import AuditEvent
from app.schemas.audit import AuditEventPage, AuditEventResponse

router = APIRouter(prefix="/audit")
AuditViewer = Annotated[AuthenticatedUser, Depends(require_permission("audit.view"))]


@router.get("/events", response_model=AuditEventPage)
async def events(
    current_user: AuditViewer,
    session: SessionDependency,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    action: str | None = Query(default=None, min_length=1, max_length=100),
    entity_type: str | None = Query(default=None, min_length=1, max_length=100),
) -> AuditEventPage:
    statement = select(AuditEvent).where(AuditEvent.tenant_id == current_user.tenant_id)
    if action is not None:
        statement = statement.where(AuditEvent.action == action)
    if entity_type is not None:
        statement = statement.where(AuditEvent.entity_type == entity_type)
    rows = await session.scalars(
        statement.order_by(AuditEvent.created_at.desc()).offset(offset).limit(limit)
    )
    return AuditEventPage(
        items=[AuditEventResponse.model_validate(row) for row in rows], limit=limit, offset=offset
    )
