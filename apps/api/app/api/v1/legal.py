import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import AuthenticatedUser, SessionDependency, require_permission
from app.schemas.dashboard import LegalDashboardResponse
from app.schemas.legal import (
    CourtDecisionCreate,
    CourtDecisionResponse,
    EnforcementProceedingCreate,
    EnforcementProceedingResponse,
    LegalCaseCreate,
    LegalCaseResponse,
    LegalObligationCreate,
    LegalObligationResponse,
    ObligationStatusChange,
    PenaltyExposureResponse,
    PenaltyRuleCreate,
    PenaltyRuleResponse,
)
from app.services.legal import (
    InvalidStatusTransitionError,
    LegalConflictError,
    LegalResourceNotFoundError,
    LegalService,
)

router = APIRouter(prefix="/legal")
LegalManager = Annotated[AuthenticatedUser, Depends(require_permission("legal.manage"))]


@router.get("/dashboard", response_model=LegalDashboardResponse)
async def dashboard(user: LegalManager, session: SessionDependency) -> LegalDashboardResponse:
    return LegalDashboardResponse(
        **await LegalService(session).dashboard(user.tenant_id, date.today())
    )


def service_error(exc: Exception) -> HTTPException:
    if isinstance(exc, LegalConflictError):
        return HTTPException(409, "A legal record with this reference already exists.")
    if isinstance(exc, LegalResourceNotFoundError):
        return HTTPException(404, "The requested legal resource is not available in this tenant.")
    return HTTPException(422, "This obligation status transition is not allowed.")


@router.get("/enforcements", response_model=list[EnforcementProceedingResponse])
async def enforcements(
    user: LegalManager, session: SessionDependency
) -> list[EnforcementProceedingResponse]:
    return [
        EnforcementProceedingResponse.model_validate(item)
        for item in await LegalService(session).list_enforcements(user.tenant_id)
    ]


@router.post("/enforcements", response_model=EnforcementProceedingResponse, status_code=201)
async def create_enforcement(
    data: EnforcementProceedingCreate, user: LegalManager, session: SessionDependency
) -> EnforcementProceedingResponse:
    try:
        return EnforcementProceedingResponse.model_validate(
            await LegalService(session).create_enforcement(user.tenant_id, user.id, data)
        )
    except (LegalConflictError, LegalResourceNotFoundError) as exc:
        raise service_error(exc) from exc


@router.get("/penalties/rules", response_model=list[PenaltyRuleResponse])
async def penalty_rules(
    user: LegalManager, session: SessionDependency
) -> list[PenaltyRuleResponse]:
    return [
        PenaltyRuleResponse.model_validate(item)
        for item in await LegalService(session).list_penalty_rules(user.tenant_id)
    ]


@router.post("/penalties/rules", response_model=PenaltyRuleResponse, status_code=201)
async def create_penalty_rule(
    data: PenaltyRuleCreate, user: LegalManager, session: SessionDependency
) -> PenaltyRuleResponse:
    try:
        return PenaltyRuleResponse.model_validate(
            await LegalService(session).create_penalty_rule(user.tenant_id, user.id, data)
        )
    except (LegalConflictError, LegalResourceNotFoundError) as exc:
        raise service_error(exc) from exc


@router.get("/penalties/rules/{rule_id}/exposure", response_model=PenaltyExposureResponse)
async def penalty_exposure(
    rule_id: uuid.UUID,
    user: LegalManager,
    session: SessionDependency,
    as_of_date: date | None = None,
) -> PenaltyExposureResponse:
    effective_date = as_of_date or date.today()
    try:
        rule, amount = await LegalService(session).penalty_exposure(
            user.tenant_id, rule_id, effective_date
        )
    except LegalResourceNotFoundError as exc:
        raise service_error(exc) from exc
    return PenaltyExposureResponse(rule_id=rule.id, as_of_date=effective_date, amount=amount)


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
