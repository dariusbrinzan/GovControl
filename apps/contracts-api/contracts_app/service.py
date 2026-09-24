import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from contracts_app.models import (
    Contract,
    ContractAuditEvent,
    ContractStatus,
    ContractStatusHistory,
    OutboxEvent,
)
from contracts_app.schemas import ContractCreate


class ContractNotFoundError(Exception):
    pass


class ContractConflictError(Exception):
    pass


class InvalidContractTransitionError(Exception):
    pass


ALLOWED_TRANSITIONS: dict[ContractStatus, set[ContractStatus]] = {
    ContractStatus.DRAFT: {ContractStatus.IN_REVIEW, ContractStatus.CANCELLED},
    ContractStatus.IN_REVIEW: {
        ContractStatus.DRAFT,
        ContractStatus.ACTIVE,
        ContractStatus.CANCELLED,
    },
    ContractStatus.ACTIVE: {
        ContractStatus.SUSPENDED,
        ContractStatus.COMPLETED,
        ContractStatus.TERMINATED,
    },
    ContractStatus.SUSPENDED: {ContractStatus.ACTIVE, ContractStatus.TERMINATED},
    ContractStatus.COMPLETED: set(),
    ContractStatus.TERMINATED: set(),
    ContractStatus.CANCELLED: set(),
}


class ContractService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self, tenant_id: uuid.UUID, limit: int, offset: int) -> list[Contract]:
        return list(
            await self.session.scalars(
                select(Contract)
                .where(Contract.tenant_id == tenant_id)
                .order_by(Contract.created_at.desc(), Contract.id)
                .offset(offset)
                .limit(limit)
            )
        )

    async def get(self, tenant_id: uuid.UUID, contract_id: uuid.UUID) -> Contract:
        item = await self.session.scalar(
            select(Contract).where(Contract.id == contract_id, Contract.tenant_id == tenant_id)
        )
        if item is None:
            raise ContractNotFoundError
        return item

    async def create(
        self, tenant_id: uuid.UUID, actor_id: uuid.UUID, data: ContractCreate
    ) -> Contract:
        existing = await self.session.scalar(
            select(Contract.id).where(
                Contract.tenant_id == tenant_id,
                Contract.contract_number == data.contract_number,
            )
        )
        if existing is not None:
            raise ContractConflictError
        item = Contract(
            tenant_id=tenant_id,
            created_by=actor_id,
            **data.model_dump(),
        )
        self.session.add(item)
        await self.session.flush()
        payload = {"contract_number": item.contract_number, "status": item.status.value}
        self.session.add_all(
            [
                ContractAuditEvent(
                    tenant_id=tenant_id,
                    actor_user_id=actor_id,
                    action="CREATED",
                    entity_type="Contract",
                    entity_id=item.id,
                    payload=payload,
                ),
                OutboxEvent(
                    tenant_id=tenant_id,
                    event_type="contracts.contract.created.v1",
                    aggregate_type="Contract",
                    aggregate_id=item.id,
                    payload={"contract_id": str(item.id), **payload},
                ),
            ]
        )
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ContractConflictError from exc
        await self.session.refresh(item)
        return item

    async def change_status(
        self,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        contract_id: uuid.UUID,
        new_status: ContractStatus,
    ) -> Contract:
        item = await self.get(tenant_id, contract_id)
        if new_status not in ALLOWED_TRANSITIONS[item.status]:
            raise InvalidContractTransitionError
        old_status = item.status
        item.status = new_status
        payload = {"old_status": old_status.value, "new_status": new_status.value}
        self.session.add_all(
            [
                ContractStatusHistory(
                    tenant_id=tenant_id,
                    contract_id=item.id,
                    old_status=old_status,
                    new_status=new_status,
                    actor_user_id=actor_id,
                ),
                ContractAuditEvent(
                    tenant_id=tenant_id,
                    actor_user_id=actor_id,
                    action="STATUS_CHANGED",
                    entity_type="Contract",
                    entity_id=item.id,
                    payload=payload,
                ),
                OutboxEvent(
                    tenant_id=tenant_id,
                    event_type="contracts.contract.status-changed.v1",
                    aggregate_type="Contract",
                    aggregate_id=item.id,
                    payload={"contract_id": str(item.id), **payload},
                ),
            ]
        )
        await self.session.commit()
        await self.session.refresh(item)
        return item

    async def dashboard(self, tenant_id: uuid.UUID, today: date) -> dict[str, int | Decimal]:
        active = Contract.status == ContractStatus.ACTIVE
        row = (
            await self.session.execute(
                select(
                    func.count(),
                    func.count().filter(active),
                    func.count().filter(
                        active,
                        Contract.end_date >= today,
                        Contract.end_date <= today + timedelta(days=30),
                    ),
                    func.coalesce(func.sum(Contract.value).filter(active), 0),
                ).where(Contract.tenant_id == tenant_id)
            )
        ).one()
        return {
            "total_contracts": int(row[0]),
            "active_contracts": int(row[1]),
            "expiring_within_30_days": int(row[2]),
            "total_active_value": Decimal(row[3]),
        }
