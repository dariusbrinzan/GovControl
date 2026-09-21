from fastapi import APIRouter
from sqlalchemy import select

from app.core.security import CurrentUserDependency, SessionDependency
from app.models.audit import AuditEvent

router = APIRouter(prefix="/audit")


@router.get("/events")
async def events(
    current_user: CurrentUserDependency, session: SessionDependency
) -> list[dict[str, str]]:
    rows = await session.scalars(
        select(AuditEvent)
        .where(AuditEvent.tenant_id == current_user.tenant_id)
        .order_by(AuditEvent.created_at.desc())
        .limit(100)
    )
    return [
        {
            "id": str(row.id),
            "action": row.action,
            "entity_type": row.entity_type,
            "entity_id": str(row.entity_id),
            "timestamp": row.created_at.isoformat(),
        }
        for row in rows
    ]
