import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import AuthenticatedUser, SessionDependency, require_permission
from app.schemas.legal import (
    CourtDecisionCreate,
    CourtDecisionResponse,
    LegalCaseCreate,
    LegalCaseResponse,
    LegalObligationCreate,
    LegalObligationResponse,
    ObligationStatusChange,
)
from app.services.legal import (
    InvalidStatusTransitionError,
    LegalConflictError,
    LegalResourceNotFoundError,
    LegalService,
)

router = APIRouter(prefix="/legal")
LegalManager = Annotated[AuthenticatedUser, Depends(require_permission("legal.manage"))]


def service_error(exc: Exception) -> HTTPException:
    if isinstance(exc, LegalConflictError):
        return HTTPException(409, "A legal record with this reference already exists.")
    if isinstance(exc, LegalResourceNotFoundError):
        return HTTPException(404, "The requested legal resource is not available in this tenant.")
    return HTTPException(422, "This obligation status transition is not allowed.")


@router.get("/cases", response_model=list[LegalCaseResponse])
async def cases(user: LegalManager, session: SessionDependency) -> list[LegalCaseResponse]:
    return [
        LegalCaseResponse.model_validate(x)
        for x in await LegalService(session).list_cases(user.tenant_id)
    ]


@router.post("/cases", response_model=LegalCaseResponse, status_code=201)
async def create_case(
    data: LegalCaseCreate, user: LegalManager, session: SessionDependency
) -> LegalCaseResponse:
    try:
        return LegalCaseResponse.model_validate(
            await LegalService(session).create_case(user.tenant_id, user.id, data)
        )
    except (LegalConflictError, LegalResourceNotFoundError, InvalidStatusTransitionError) as exc:
        raise service_error(exc) from exc


@router.post("/cases/{case_id}/decisions", response_model=CourtDecisionResponse, status_code=201)
async def create_decision(
    case_id: uuid.UUID, data: CourtDecisionCreate, user: LegalManager, session: SessionDependency
) -> CourtDecisionResponse:
    try:
        return CourtDecisionResponse.model_validate(
            await LegalService(session).create_decision(user.tenant_id, user.id, case_id, data)
        )
    except (LegalConflictError, LegalResourceNotFoundError, InvalidStatusTransitionError) as exc:
        raise service_error(exc) from exc


@router.get("/obligations", response_model=list[LegalObligationResponse])
async def obligations(
    user: LegalManager, session: SessionDependency
) -> list[LegalObligationResponse]:
    return [
        LegalObligationResponse.model_validate(x)
        for x in await LegalService(session).list_obligations(user.tenant_id)
    ]


@router.get("/obligations/overdue", response_model=list[LegalObligationResponse])
async def overdue_obligations(
    user: LegalManager, session: SessionDependency
) -> list[LegalObligationResponse]:
    items = await LegalService(session).overdue_obligations(user.tenant_id, date.today())
    return [LegalObligationResponse.model_validate(item) for item in items]


@router.post("/obligations", response_model=LegalObligationResponse, status_code=201)
async def create_obligation(
    data: LegalObligationCreate, user: LegalManager, session: SessionDependency
) -> LegalObligationResponse:
    try:
        return LegalObligationResponse.model_validate(
            await LegalService(session).create_obligation(user.tenant_id, user.id, data)
        )
    except (LegalConflictError, LegalResourceNotFoundError, InvalidStatusTransitionError) as exc:
        raise service_error(exc) from exc


@router.patch("/obligations/{obligation_id}/status", response_model=LegalObligationResponse)
async def change_status(
    obligation_id: uuid.UUID,
    data: ObligationStatusChange,
    user: LegalManager,
    session: SessionDependency,
) -> LegalObligationResponse:
    try:
        return LegalObligationResponse.model_validate(
            await LegalService(session).change_status(
                user.tenant_id, user.id, obligation_id, data.status
            )
        )
    except (LegalConflictError, LegalResourceNotFoundError, InvalidStatusTransitionError) as exc:
        raise service_error(exc) from exc
