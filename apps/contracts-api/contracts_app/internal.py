import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from contracts_app.database import get_session
from contracts_app.models import Contract, ContractAmendment, ContractMilestone
from contracts_app.schemas import ContractResponse
from contracts_app.security import CurrentUser, InternalService
from contracts_app.service import ContractNotFoundError, ContractService

router = APIRouter(prefix="/internal", include_in_schema=False)
Session = Annotated[AsyncSession, Depends(get_session)]
TenantHeader = Annotated[uuid.UUID, Header(alias="X-Tenant-ID")]


@router.get("/contracts/{contract_id}", response_model=ContractResponse)
async def internal_contract(
    contract_id: uuid.UUID,
    tenant_id: TenantHeader,
    _: InternalService,
    session: Session,
) -> ContractResponse:
    """Resolve contract ownership for an authenticated platform service."""
    try:
        contract = await ContractService(session).get(tenant_id, contract_id)
    except ContractNotFoundError as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Contract not found in this tenant."
        ) from exc
    return ContractResponse.model_validate(contract)


@router.get("/resources/{resource_type}/{resource_id}", status_code=status.HTTP_204_NO_CONTENT)
async def internal_resource(
    resource_type: str,
    resource_id: uuid.UUID,
    tenant_id: TenantHeader,
    _: InternalService,
    user: CurrentUser,
    session: Session,
) -> None:
    """Validate a contractual resource for an authenticated internal caller."""
    if tenant_id != user.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Resource not found in this tenant.")
    models: dict[str, type[Contract | ContractAmendment | ContractMilestone]] = {
        "Contract": Contract,
        "ContractAmendment": ContractAmendment,
        "ContractMilestone": ContractMilestone,
    }
    model = models.get(resource_type)
    if model is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Resource not found in this tenant.")
    exists = await session.scalar(
        select(model.id).where(model.id == resource_id, model.tenant_id == user.tenant_id)
    )
    if exists is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Resource not found in this tenant.")
