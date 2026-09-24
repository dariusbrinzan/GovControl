import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.security import AuthenticatedUser, SessionDependency, require_permission
from app.models.legal import ObligationStatus
from app.schemas.analytics import AnalyticsFilterOptionsResponse, LegalAnalyticsDashboardResponse
from app.services.analytics import AnalyticsFilterError, AnalyticsService

router = APIRouter(prefix="/legal/analytics")
LegalReporter = Annotated[AuthenticatedUser, Depends(require_permission("legal.report"))]


@router.get("/filters", response_model=AnalyticsFilterOptionsResponse)
async def analytics_filters(
    user: LegalReporter, session: SessionDependency
) -> AnalyticsFilterOptionsResponse:
    return await AnalyticsService(session).filter_options(user.tenant_id)


@router.get("/dashboard", response_model=LegalAnalyticsDashboardResponse)
async def analytics_dashboard(
    user: LegalReporter,
    session: SessionDependency,
    date_from: date | None = None,
    date_to: date | None = None,
    department_id: uuid.UUID | None = None,
    responsible_user_id: uuid.UUID | None = None,
    court: str | None = Query(default=None, min_length=1, max_length=255),
    obligation_status: ObligationStatus | None = None,
) -> LegalAnalyticsDashboardResponse:
    try:
        return await AnalyticsService(session).dashboard(
            tenant_id=user.tenant_id,
            today=date.today(),
            date_from=date_from,
            date_to=date_to,
            department_id=department_id,
            responsible_user_id=responsible_user_id,
            court=court,
            status=obligation_status,
        )
    except AnalyticsFilterError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
