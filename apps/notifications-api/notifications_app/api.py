import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from notifications_app.database import get_session
from notifications_app.models import NotificationStatus
from notifications_app.schemas import (
    AuditResponse,
    BulkMutationResult,
    DeliveryResponse,
    InternalNotificationCreate,
    InternalScheduleCreate,
    NotificationPage,
    PreferenceInput,
    PreferenceResponse,
    RetryResult,
    TemplateCreate,
    TemplateResponse,
    UnreadCount,
    UserContext,
)
from notifications_app.security import require_internal_service, require_permission
from notifications_app.service import (
    NotificationConflictError,
    NotificationNotFoundError,
    NotificationService,
    TemplateValidationError,
)

router = APIRouter()
Session = Annotated[AsyncSession, Depends(get_session)]
Reader = Annotated[UserContext, Depends(require_permission("notifications.read"))]
Manager = Annotated[UserContext, Depends(require_permission("notifications.manage"))]
PreferenceOwner = Annotated[
    UserContext, Depends(require_permission("notifications.preferences"))
]
Administrator = Annotated[UserContext, Depends(require_permission("notifications.admin"))]
Auditor = Annotated[UserContext, Depends(require_permission("notifications.audit"))]


def map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, NotificationNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, "Notification resource is not available.")
    if isinstance(exc, (NotificationConflictError, TemplateValidationError, IntegrityError)):
        return HTTPException(status.HTTP_409_CONFLICT, str(exc) or "Notification conflict.")
    return HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Notification operation failed.")


@router.get("/notifications", response_model=NotificationPage)
async def notifications(
    user: Reader,
    session: Session,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
    notification_status: Annotated[NotificationStatus | None, Query(alias="status")] = None,
    category: str | None = None,
    severity: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
) -> NotificationPage:
    items, total = await NotificationService(session).page(
        user.tenant_id,
        user.id,
        limit=limit,
        offset=offset,
        status=notification_status,
        category=category,
        severity=severity,
        created_from=created_from,
        created_to=created_to,
    )
    return NotificationPage(items=items, total=total, limit=limit, offset=offset)


@router.get("/notifications/unread-count", response_model=UnreadCount)
async def unread_count(user: Reader, session: Session) -> UnreadCount:
    count = await NotificationService(session).unread_count(user.tenant_id, user.id)
    return UnreadCount(count=count)


async def mutate_status(
    notification_id: uuid.UUID,
    target: NotificationStatus,
    user: UserContext,
    session: AsyncSession,
    audit_action: str | None = None,
) -> object:
    try:
        return await NotificationService(session).set_status(
            user.tenant_id, user.id, notification_id, target, audit_action
        )
    except (NotificationNotFoundError, NotificationConflictError) as exc:
        raise map_error(exc) from exc


@router.patch("/notifications/{notification_id}/read")
async def mark_read(notification_id: uuid.UUID, user: Manager, session: Session) -> object:
    return await mutate_status(notification_id, NotificationStatus.READ, user, session)


@router.patch("/notifications/{notification_id}/unread")
async def mark_unread(notification_id: uuid.UUID, user: Manager, session: Session) -> object:
    return await mutate_status(notification_id, NotificationStatus.UNREAD, user, session)


@router.patch("/notifications/{notification_id}/archive")
async def archive(notification_id: uuid.UUID, user: Manager, session: Session) -> object:
    return await mutate_status(notification_id, NotificationStatus.ARCHIVED, user, session)


@router.patch("/notifications/{notification_id}/restore")
async def restore(notification_id: uuid.UUID, user: Manager, session: Session) -> object:
    return await mutate_status(
        notification_id, NotificationStatus.UNREAD, user, session, "RESTORED"
    )


@router.post("/notifications/mark-all-read", response_model=BulkMutationResult)
async def mark_all_read(user: Manager, session: Session) -> BulkMutationResult:
    return BulkMutationResult(
        updated=await NotificationService(session).mark_all_read(user.tenant_id, user.id)
    )


@router.get("/notifications/preferences", response_model=list[PreferenceResponse])
async def preferences(user: PreferenceOwner, session: Session) -> list[PreferenceResponse]:
    return [
        PreferenceResponse.model_validate(item)
        for item in await NotificationService(session).preferences(user.tenant_id, user.id)
    ]


@router.put("/notifications/preferences", response_model=PreferenceResponse)
async def set_preference(
    value: PreferenceInput, user: PreferenceOwner, session: Session
) -> PreferenceResponse:
    item = await NotificationService(session).set_preference(user.tenant_id, user.id, value)
    return PreferenceResponse.model_validate(item)


@router.get("/notifications/templates", response_model=list[TemplateResponse])
async def templates(user: Administrator, session: Session) -> list[TemplateResponse]:
    del user
    return [
        TemplateResponse.model_validate(item)
        for item in await NotificationService(session).templates()
    ]


@router.post("/notifications/templates", response_model=TemplateResponse, status_code=201)
async def create_template(
    value: TemplateCreate, user: Administrator, session: Session
) -> TemplateResponse:
    try:
        item = await NotificationService(session).create_template(
            user.tenant_id, user.id, **value.model_dump(mode="json")
        )
    except (TemplateValidationError, IntegrityError) as exc:
        await session.rollback()
        raise map_error(exc) from exc
    return TemplateResponse.model_validate(item)


@router.get("/notifications/audit", response_model=list[AuditResponse])
async def audit(
    user: Auditor, session: Session, limit: Annotated[int, Query(ge=1, le=500)] = 100
) -> list[AuditResponse]:
    return [
        AuditResponse.model_validate(item)
        for item in await NotificationService(session).audit_events(user.tenant_id, limit)
    ]


@router.get("/notifications/deliveries", response_model=list[DeliveryResponse])
async def deliveries(
    user: Administrator, session: Session, limit: Annotated[int, Query(ge=1, le=500)] = 100
) -> list[DeliveryResponse]:
    return [
        DeliveryResponse.model_validate(item)
        for item in await NotificationService(session).deliveries(user.tenant_id, limit)
    ]


@router.post("/notifications/deliveries/{delivery_id}/retry", response_model=RetryResult)
async def retry_delivery(
    delivery_id: uuid.UUID, user: Administrator, session: Session
) -> RetryResult:
    try:
        queued = await NotificationService(session).retry_delivery(
            user.tenant_id, delivery_id, user.id
        )
    except (NotificationNotFoundError, NotificationConflictError) as exc:
        raise map_error(exc) from exc
    return RetryResult(queued=queued)


@router.post(
    "/internal/notifications",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_internal_service)],
)
async def internal_create(value: InternalNotificationCreate, session: Session) -> dict[str, object]:
    try:
        item, created = await NotificationService(session).ingest(value)
    except (NotificationNotFoundError, NotificationConflictError, TemplateValidationError) as exc:
        raise map_error(exc) from exc
    return {"id": str(item.id), "created": created}


@router.post(
    "/internal/notifications/schedules",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_internal_service)],
)
async def internal_schedule(
    value: InternalScheduleCreate, session: Session
) -> dict[str, object]:
    try:
        item, created = await NotificationService(session).schedule(value)
    except NotificationConflictError as exc:
        raise map_error(exc) from exc
    return {"id": str(item.id), "created": created}
