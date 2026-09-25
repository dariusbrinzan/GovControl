import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from contracts_app.database import get_session
from contracts_app.schemas import ContractResponse
from contracts_app.security import InternalService
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
