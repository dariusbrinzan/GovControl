import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from contracts_app.database import get_session
from contracts_app.schemas import (
    ContractCreate,
    ContractDashboard,
    ContractResponse,
    ContractStatusChange,
)
from contracts_app.security import ContractManager, ContractReporter
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
    return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Status transition is not allowed.")


@router.get("", response_model=list[ContractResponse])
async def list_contracts(
    user: ContractManager,
    session: Session,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[ContractResponse]:
    return [
        ContractResponse.model_validate(item)
        for item in await ContractService(session).list(user.tenant_id, limit, offset)
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
    values = await ContractService(session).dashboard(user.tenant_id, date.today())
    return ContractDashboard(**values)


@router.get("/{contract_id}", response_model=ContractResponse)
async def contract_detail(
    contract_id: uuid.UUID, user: ContractManager, session: Session
) -> ContractResponse:
    try:
        item = await ContractService(session).get(user.tenant_id, contract_id)
    except ContractNotFoundError as exc:
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
