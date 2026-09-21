import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import (
    AuthenticatedUser,
    CurrentUserDependency,
    SessionDependency,
    require_permission,
)
from app.schemas.notification import NotificationDispatchResponse, NotificationResponse
from app.services.notifications import NotificationNotFoundError, NotificationService

router = APIRouter(prefix="/notifications")
LegalManager = Annotated[AuthenticatedUser, Depends(require_permission("legal.manage"))]


@router.get("", response_model=list[NotificationResponse])
async def notifications(
    user: CurrentUserDependency, session: SessionDependency
) -> list[NotificationResponse]:
    return [
        NotificationResponse.model_validate(item)
        for item in await NotificationService(session).list_for_user(user.tenant_id, user.id)
    ]


@router.patch("/{notification_id}/read", response_model=NotificationResponse)
async def mark_notification_read(
    notification_id: uuid.UUID, user: CurrentUserDependency, session: SessionDependency
) -> NotificationResponse:
    try:
        item = await NotificationService(session).mark_read(
            user.tenant_id, user.id, notification_id
        )
    except NotificationNotFoundError as exc:
        raise HTTPException(404, "The requested notification is not available.") from exc
    return NotificationResponse.model_validate(item)


@router.post("/dispatch/deadline-reminders", response_model=NotificationDispatchResponse)
async def dispatch_deadline_reminders(
    user: LegalManager, session: SessionDependency, as_of_date: date | None = None
) -> NotificationDispatchResponse:
    created = await NotificationService(session).dispatch_deadline_reminders(
        user.tenant_id, user.id, as_of_date or date.today()
    )
    return NotificationDispatchResponse(created=created)
