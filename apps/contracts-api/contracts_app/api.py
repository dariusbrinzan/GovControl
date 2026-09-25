import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from contracts_app.database import get_session
from contracts_app.models import ContractStatus
from contracts_app.schemas import (
    AmendmentCreate,
    AmendmentResponse,
    AuditEventPage,
    AuditEventResponse,
    ContractCreate,
    ContractDashboard,
    ContractDetailResponse,
    ContractPage,
    ContractResponse,
    ContractStatusChange,
    ContractUpdate,
    MilestoneCreate,
    MilestoneResponse,
    MilestoneStatusChange,
    NotificationResponse,
    ObligationCreate,
    ObligationResponse,
    ObligationStatusChange,
    PartyCreate,
    PartyResponse,
    PaymentCreate,
    PaymentResponse,
    PaymentStatusChange,
)
from contracts_app.security import ContractAuditor, ContractManager, ContractReporter
from contracts_app.service import (
    ContractConflictError,
    ContractNotFoundError,
    ContractService,
    InvalidContractTransitionError,
)

router = APIRouter(prefix="/contracts", tags=["contracts"])
Session = Annotated[AsyncSession, Depends(get_session)]


def map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ContractNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, "Contract not found in this tenant.")
    if isinstance(exc, ContractConflictError):
        return HTTPException(status.HTTP_409_CONFLICT, "Contract number already exists.")
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Status transition is not allowed.")


@router.get("", response_model=list[ContractResponse])
async def list_contracts(
    user: ContractManager,
    session: Session,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[ContractResponse]:
    return [
        ContractResponse.model_validate(item)
        for item in await ContractService(session).list_contracts(user.tenant_id, limit, offset)
    ]


@router.post("", response_model=ContractResponse, status_code=status.HTTP_201_CREATED)
async def create_contract(
    data: ContractCreate, user: ContractManager, session: Session
) -> ContractResponse:
    try:
        item = await ContractService(session).create(user.tenant_id, user.id, data)
    except ContractConflictError as exc:
        raise map_error(exc) from exc
    return ContractResponse.model_validate(item)


@router.get("/dashboard", response_model=ContractDashboard)
async def dashboard(user: ContractReporter, session: Session) -> ContractDashboard:
    return await ContractService(session).dashboard(user.tenant_id, date.today())


@router.get("/page", response_model=ContractPage)
async def contract_page(
    user: ContractManager,
    session: Session,
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    search: str | None = Query(None, min_length=1, max_length=200),
    status_filter: Annotated[ContractStatus | None, Query(alias="status")] = None,
) -> ContractPage:
    items, total = await ContractService(session).page_contracts(
        user.tenant_id, limit, offset, search, status_filter
    )
    return ContractPage(
        items=[ContractResponse.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/notifications", response_model=list[NotificationResponse])
async def notifications(
    user: ContractReporter,
    session: Session,
    limit: int = Query(100, ge=1, le=500),
    unread_only: bool = False,
) -> list[NotificationResponse]:
    items = await ContractService(session).notifications(user.tenant_id, limit, unread_only)
    return [NotificationResponse.model_validate(item) for item in items]


@router.patch("/notifications/{notification_id}/read", response_model=NotificationResponse)
async def mark_notification_read(
    notification_id: uuid.UUID, user: ContractManager, session: Session
) -> NotificationResponse:
    try:
        item = await ContractService(session).mark_notification_read(
            user.tenant_id, notification_id
        )
    except ContractNotFoundError as exc:
        raise map_error(exc) from exc
    return NotificationResponse.model_validate(item)


@router.get("/audit", response_model=AuditEventPage)
async def audit_events(
    user: ContractAuditor,
    session: Session,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> AuditEventPage:
    items, total = await ContractService(session).audit_events(user.tenant_id, limit, offset)
    return AuditEventPage(
        items=[AuditEventResponse.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{contract_id}/overview", response_model=ContractDetailResponse)
async def contract_overview(
    contract_id: uuid.UUID, user: ContractManager, session: Session
) -> ContractDetailResponse:
    service = ContractService(session)
    try:
        contract = await service.get(user.tenant_id, contract_id)
        party_rows = await service.parties(user.tenant_id, contract_id)
        amendments = await service.amendments(user.tenant_id, contract_id)
        milestones = await service.milestones(user.tenant_id, contract_id)
        obligations = await service.obligations(user.tenant_id, contract_id)
        payments = await service.payments(user.tenant_id, contract_id)
    except ContractNotFoundError as exc:
        raise map_error(exc) from exc
    return ContractDetailResponse(
        contract=ContractResponse.model_validate(contract),
        parties=[
            PartyResponse.model_validate(party).model_copy(update={"role": role})
            for party, role in party_rows
        ],
        amendments=[AmendmentResponse.model_validate(item) for item in amendments],
        milestones=[MilestoneResponse.model_validate(item) for item in milestones],
        obligations=[ObligationResponse.model_validate(item) for item in obligations],
        payments=[PaymentResponse.model_validate(item) for item in payments],
    )


@router.get("/{contract_id}/parties", response_model=list[PartyResponse])
async def list_parties(
    contract_id: uuid.UUID, user: ContractManager, session: Session
) -> list[PartyResponse]:
    try:
        rows = await ContractService(session).parties(user.tenant_id, contract_id)
    except ContractNotFoundError as exc:
        raise map_error(exc) from exc
    return [
        PartyResponse.model_validate(party).model_copy(update={"role": role})
        for party, role in rows
    ]


@router.post("/{contract_id}/parties", response_model=PartyResponse, status_code=201)
async def add_party(
    contract_id: uuid.UUID, data: PartyCreate, user: ContractManager, session: Session
) -> PartyResponse:
    try:
        party, role = await ContractService(session).add_party(
            user.tenant_id, user.id, contract_id, data
        )
    except ContractNotFoundError as exc:
        raise map_error(exc) from exc
    return PartyResponse.model_validate(party).model_copy(update={"role": role})


@router.get("/{contract_id}/amendments", response_model=list[AmendmentResponse])
async def list_amendments(
    contract_id: uuid.UUID, user: ContractManager, session: Session
) -> list[AmendmentResponse]:
    try:
        items = await ContractService(session).amendments(user.tenant_id, contract_id)
    except ContractNotFoundError as exc:
        raise map_error(exc) from exc
    return [AmendmentResponse.model_validate(item) for item in items]


@router.post("/{contract_id}/amendments", response_model=AmendmentResponse, status_code=201)
async def add_amendment(
    contract_id: uuid.UUID, data: AmendmentCreate, user: ContractManager, session: Session
) -> AmendmentResponse:
    try:
        item = await ContractService(session).add_amendment(
            user.tenant_id, user.id, contract_id, data
        )
    except (ContractNotFoundError, ContractConflictError) as exc:
        raise map_error(exc) from exc
    return AmendmentResponse.model_validate(item)


@router.get("/{contract_id}/milestones", response_model=list[MilestoneResponse])
async def list_milestones(
    contract_id: uuid.UUID, user: ContractManager, session: Session
) -> list[MilestoneResponse]:
    try:
        items = await ContractService(session).milestones(user.tenant_id, contract_id)
    except ContractNotFoundError as exc:
        raise map_error(exc) from exc
    return [MilestoneResponse.model_validate(item) for item in items]


@router.post("/{contract_id}/milestones", response_model=MilestoneResponse, status_code=201)
async def add_milestone(
    contract_id: uuid.UUID, data: MilestoneCreate, user: ContractManager, session: Session
) -> MilestoneResponse:
    try:
        item = await ContractService(session).add_milestone(
            user.tenant_id, user.id, contract_id, data
        )
    except ContractNotFoundError as exc:
        raise map_error(exc) from exc
    return MilestoneResponse.model_validate(item)


@router.patch(
    "/{contract_id}/milestones/{item_id}/status", response_model=MilestoneResponse
)
async def change_milestone_status(
    contract_id: uuid.UUID,
    item_id: uuid.UUID,
    data: MilestoneStatusChange,
    user: ContractManager,
    session: Session,
) -> MilestoneResponse:
    try:
        item = await ContractService(session).change_milestone_status(
            user.tenant_id, user.id, contract_id, item_id, data.status
        )
    except (ContractNotFoundError, InvalidContractTransitionError) as exc:
        raise map_error(exc) from exc
    return MilestoneResponse.model_validate(item)


@router.get("/{contract_id}/obligations", response_model=list[ObligationResponse])
async def list_obligations(
    contract_id: uuid.UUID, user: ContractManager, session: Session
) -> list[ObligationResponse]:
    try:
        items = await ContractService(session).obligations(user.tenant_id, contract_id)
    except ContractNotFoundError as exc:
        raise map_error(exc) from exc
    return [ObligationResponse.model_validate(item) for item in items]


@router.post("/{contract_id}/obligations", response_model=ObligationResponse, status_code=201)
async def add_obligation(
    contract_id: uuid.UUID, data: ObligationCreate, user: ContractManager, session: Session
) -> ObligationResponse:
    try:
        item = await ContractService(session).add_obligation(
            user.tenant_id, user.id, contract_id, data
        )
    except ContractNotFoundError as exc:
        raise map_error(exc) from exc
    return ObligationResponse.model_validate(item)


@router.patch(
    "/{contract_id}/obligations/{item_id}/status", response_model=ObligationResponse
)
async def change_obligation_status(
    contract_id: uuid.UUID,
    item_id: uuid.UUID,
    data: ObligationStatusChange,
    user: ContractManager,
    session: Session,
) -> ObligationResponse:
    try:
        item = await ContractService(session).change_obligation_status(
            user.tenant_id, user.id, contract_id, item_id, data.status
        )
    except (ContractNotFoundError, InvalidContractTransitionError) as exc:
        raise map_error(exc) from exc
    return ObligationResponse.model_validate(item)


@router.get("/{contract_id}/payments", response_model=list[PaymentResponse])
async def list_payments(
    contract_id: uuid.UUID, user: ContractManager, session: Session
) -> list[PaymentResponse]:
    try:
        items = await ContractService(session).payments(user.tenant_id, contract_id)
    except ContractNotFoundError as exc:
        raise map_error(exc) from exc
    return [PaymentResponse.model_validate(item) for item in items]


@router.post("/{contract_id}/payments", response_model=PaymentResponse, status_code=201)
async def add_payment(
    contract_id: uuid.UUID, data: PaymentCreate, user: ContractManager, session: Session
) -> PaymentResponse:
    try:
        item = await ContractService(session).add_payment(
            user.tenant_id, user.id, contract_id, data
        )
    except ContractNotFoundError as exc:
        raise map_error(exc) from exc
    return PaymentResponse.model_validate(item)


@router.patch("/{contract_id}/payments/{item_id}/status", response_model=PaymentResponse)
async def change_payment_status(
    contract_id: uuid.UUID,
    item_id: uuid.UUID,
    data: PaymentStatusChange,
    user: ContractManager,
    session: Session,
) -> PaymentResponse:
    try:
        item = await ContractService(session).change_payment_status(
            user.tenant_id, user.id, contract_id, item_id, data.status
        )
    except (ContractNotFoundError, InvalidContractTransitionError) as exc:
        raise map_error(exc) from exc
    return PaymentResponse.model_validate(item)


@router.get("/{contract_id}", response_model=ContractResponse)
async def contract_detail(
    contract_id: uuid.UUID, user: ContractManager, session: Session
) -> ContractResponse:
    try:
        item = await ContractService(session).get(user.tenant_id, contract_id)
    except ContractNotFoundError as exc:
        raise map_error(exc) from exc
    return ContractResponse.model_validate(item)


@router.patch("/{contract_id}", response_model=ContractResponse)
async def update_contract(
    contract_id: uuid.UUID,
    data: ContractUpdate,
    user: ContractManager,
    session: Session,
) -> ContractResponse:
    try:
        item = await ContractService(session).update(user.tenant_id, user.id, contract_id, data)
    except (ContractNotFoundError, ContractConflictError) as exc:
        raise map_error(exc) from exc
    return ContractResponse.model_validate(item)


@router.patch("/{contract_id}/status", response_model=ContractResponse)
async def change_status(
    contract_id: uuid.UUID,
    data: ContractStatusChange,
    user: ContractManager,
    session: Session,
) -> ContractResponse:
    try:
        item = await ContractService(session).change_status(
            user.tenant_id, user.id, contract_id, data.status
        )
    except (ContractNotFoundError, InvalidContractTransitionError) as exc:
        raise map_error(exc) from exc
    return ContractResponse.model_validate(item)
