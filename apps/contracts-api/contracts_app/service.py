import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from contracts_app.models import (
    Contract,
    ContractAmendment,
    ContractAuditEvent,
    ContractMilestone,
    ContractObligation,
    ContractParty,
    ContractPartyLink,
    ContractPayment,
    ContractStatus,
    ContractStatusHistory,
    MilestoneStatus,
    ObligationStatus,
    OutboxEvent,
    PaymentStatus,
)
from contracts_app.observability import current_request_id
from contracts_app.schemas import (
    AmendmentCreate,
    ContractCreate,
    ContractDashboard,
    ContractUpdate,
    MilestoneCreate,
    ObligationCreate,
    PartyCreate,
    PaymentCreate,
)


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

MILESTONE_TRANSITIONS: dict[MilestoneStatus, set[MilestoneStatus]] = {
    MilestoneStatus.PENDING: {
        MilestoneStatus.IN_PROGRESS,
        MilestoneStatus.COMPLETED,
        MilestoneStatus.OVERDUE,
        MilestoneStatus.CANCELLED,
    },
    MilestoneStatus.IN_PROGRESS: {
        MilestoneStatus.COMPLETED,
        MilestoneStatus.OVERDUE,
        MilestoneStatus.CANCELLED,
    },
    MilestoneStatus.OVERDUE: {
        MilestoneStatus.IN_PROGRESS,
        MilestoneStatus.COMPLETED,
        MilestoneStatus.CANCELLED,
    },
    MilestoneStatus.COMPLETED: set(),
    MilestoneStatus.CANCELLED: set(),
}

OBLIGATION_TRANSITIONS: dict[ObligationStatus, set[ObligationStatus]] = {
    ObligationStatus.OPEN: {
        ObligationStatus.IN_PROGRESS,
        ObligationStatus.COMPLETED,
        ObligationStatus.OVERDUE,
        ObligationStatus.CANCELLED,
    },
    ObligationStatus.IN_PROGRESS: {
        ObligationStatus.COMPLETED,
        ObligationStatus.OVERDUE,
        ObligationStatus.CANCELLED,
    },
    ObligationStatus.OVERDUE: {
        ObligationStatus.IN_PROGRESS,
        ObligationStatus.COMPLETED,
        ObligationStatus.CANCELLED,
    },
    ObligationStatus.COMPLETED: set(),
    ObligationStatus.CANCELLED: set(),
}

PAYMENT_TRANSITIONS: dict[PaymentStatus, set[PaymentStatus]] = {
    PaymentStatus.PLANNED: {PaymentStatus.APPROVED, PaymentStatus.CANCELLED},
    PaymentStatus.APPROVED: {
        PaymentStatus.PAID,
        PaymentStatus.REJECTED,
        PaymentStatus.CANCELLED,
    },
    PaymentStatus.PAID: set(),
    PaymentStatus.REJECTED: set(),
    PaymentStatus.CANCELLED: set(),
}


class ContractService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_contracts(
        self, tenant_id: uuid.UUID, limit: int, offset: int
    ) -> list[Contract]:
        return list(
            await self.session.scalars(
                select(Contract)
                .where(Contract.tenant_id == tenant_id)
                .order_by(Contract.created_at.desc(), Contract.id)
                .offset(offset)
                .limit(limit)
            )
        )

    async def page_contracts(
        self,
        tenant_id: uuid.UUID,
        limit: int,
        offset: int,
        search: str | None,
        status: ContractStatus | None,
    ) -> tuple[list[Contract], int]:
        filters = [Contract.tenant_id == tenant_id]
        if search:
            pattern = f"%{search.strip()}%"
            filters.append(
                or_(
                    Contract.contract_number.ilike(pattern),
                    Contract.title.ilike(pattern),
                    Contract.description.ilike(pattern),
                )
            )
        if status is not None:
            filters.append(Contract.status == status)
        total = int(
            await self.session.scalar(select(func.count()).select_from(Contract).where(*filters))
            or 0
        )
        items = list(
            await self.session.scalars(
                select(Contract)
                .where(*filters)
                .order_by(Contract.created_at.desc(), Contract.id)
                .offset(offset)
                .limit(limit)
            )
        )
        return items, total

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
                    request_id=current_request_id(),
                ),
                OutboxEvent(
                    tenant_id=tenant_id,
                    event_type="contracts.contract.created.v1",
                    aggregate_type="Contract",
                    aggregate_id=item.id,
                    payload={
                        "contract_id": str(item.id),
                        "recipient_user_id": str(actor_id),
                        **payload,
                    },
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
                    request_id=current_request_id(),
                ),
                OutboxEvent(
                    tenant_id=tenant_id,
                    event_type="contracts.contract.status-changed.v1",
                    aggregate_type="Contract",
                    aggregate_id=item.id,
                    payload={
                        "contract_id": str(item.id),
                        "recipient_user_id": str(actor_id),
                        **payload,
                    },
                ),
            ]
        )
        await self.session.commit()
        await self.session.refresh(item)
        return item

    async def update(
        self,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        contract_id: uuid.UUID,
        data: ContractUpdate,
    ) -> Contract:
        item = await self.get(tenant_id, contract_id)
        changes = data.model_dump(exclude_unset=True)
        start_date = changes.get("start_date", item.start_date)
        end_date = changes.get("end_date", item.end_date)
        signed_date = changes.get("signed_date", item.signed_date)
        if end_date < start_date or (signed_date is not None and signed_date > end_date):
            raise ContractConflictError
        for field, value in changes.items():
            setattr(item, field, value)
        payload = {"changed_fields": ",".join(sorted(changes))}
        self._record_change(tenant_id, actor_id, contract_id, "updated", payload)
        await self.session.commit()
        await self.session.refresh(item)
        return item

    async def dashboard(self, tenant_id: uuid.UUID, today: date) -> ContractDashboard:
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
                ).where(Contract.tenant_id == tenant_id)
            )
        ).one()
        status_rows = (
            await self.session.execute(
                select(Contract.status, func.count())
                .where(Contract.tenant_id == tenant_id)
                .group_by(Contract.status)
            )
        ).all()
        currency_rows = (
            await self.session.execute(
                select(Contract.currency, func.sum(Contract.value))
                .where(Contract.tenant_id == tenant_id, active)
                .group_by(Contract.currency)
            )
        ).all()
        return ContractDashboard(
            total_contracts=int(row[0]),
            active_contracts=int(row[1]),
            expiring_within_30_days=int(row[2]),
            status_counts={status.value: int(count) for status, count in status_rows},
            active_value_by_currency={
                currency: Decimal(value) for currency, value in currency_rows
            },
        )

    async def parties(
        self, tenant_id: uuid.UUID, contract_id: uuid.UUID
    ) -> list[tuple[ContractParty, str]]:
        await self.get(tenant_id, contract_id)
        rows = await self.session.execute(
            select(ContractParty, ContractPartyLink.role)
            .join(ContractPartyLink, ContractPartyLink.party_id == ContractParty.id)
            .where(
                ContractPartyLink.contract_id == contract_id,
                ContractPartyLink.tenant_id == tenant_id,
                ContractParty.tenant_id == tenant_id,
            )
            .order_by(ContractParty.name)
        )
        return [(party, role) for party, role in rows.all()]

    async def add_party(
        self,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        contract_id: uuid.UUID,
        data: PartyCreate,
    ) -> tuple[ContractParty, str]:
        await self.get(tenant_id, contract_id)
        values = data.model_dump(exclude={"role"})
        party = ContractParty(tenant_id=tenant_id, **values)
        self.session.add(party)
        await self.session.flush()
        self.session.add(
            ContractPartyLink(
                tenant_id=tenant_id,
                contract_id=contract_id,
                party_id=party.id,
                role=data.role.upper(),
            )
        )
        self._record_change(
            tenant_id, actor_id, contract_id, "party-added", {"party_id": str(party.id)}
        )
        await self.session.commit()
        await self.session.refresh(party)
        return party, data.role.upper()

    async def amendments(
        self, tenant_id: uuid.UUID, contract_id: uuid.UUID
    ) -> list[ContractAmendment]:
        await self.get(tenant_id, contract_id)
        return list(
            await self.session.scalars(
                select(ContractAmendment)
                .where(
                    ContractAmendment.contract_id == contract_id,
                    ContractAmendment.tenant_id == tenant_id,
                )
                .order_by(ContractAmendment.signed_date.desc())
            )
        )

    async def add_amendment(
        self,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        contract_id: uuid.UUID,
        data: AmendmentCreate,
    ) -> ContractAmendment:
        contract = await self.get(tenant_id, contract_id)
        if data.end_date_change is not None and data.end_date_change < contract.start_date:
            raise ContractConflictError
        item = ContractAmendment(tenant_id=tenant_id, contract_id=contract_id, **data.model_dump())
        self.session.add(item)
        if data.value_change is not None:
            contract.value += data.value_change
            if contract.value <= 0:
                raise ContractConflictError
        if data.end_date_change is not None:
            contract.end_date = data.end_date_change
        await self.session.flush()
        self._record_change(
            tenant_id,
            actor_id,
            contract_id,
            "amendment-added",
            {"amendment_id": str(item.id), "amendment_number": item.amendment_number},
        )
        await self.session.commit()
        await self.session.refresh(item)
        return item

    async def milestones(
        self, tenant_id: uuid.UUID, contract_id: uuid.UUID
    ) -> list[ContractMilestone]:
        await self.get(tenant_id, contract_id)
        return list(
            await self.session.scalars(
                select(ContractMilestone)
                .where(
                    ContractMilestone.contract_id == contract_id,
                    ContractMilestone.tenant_id == tenant_id,
                )
                .order_by(ContractMilestone.due_date)
            )
        )

    async def add_milestone(
        self,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        contract_id: uuid.UUID,
        data: MilestoneCreate,
    ) -> ContractMilestone:
        await self.get(tenant_id, contract_id)
        item = ContractMilestone(
            tenant_id=tenant_id,
            contract_id=contract_id,
            status=MilestoneStatus.PENDING,
            **data.model_dump(),
        )
        self.session.add(item)
        await self.session.flush()
        self._record_change(
            tenant_id, actor_id, contract_id, "milestone-added", {"milestone_id": str(item.id)}
        )
        await self.session.commit()
        await self.session.refresh(item)
        return item

    async def change_milestone_status(
        self,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        contract_id: uuid.UUID,
        item_id: uuid.UUID,
        new_status: MilestoneStatus,
    ) -> ContractMilestone:
        item = await self.session.scalar(
            select(ContractMilestone).where(
                ContractMilestone.id == item_id,
                ContractMilestone.contract_id == contract_id,
                ContractMilestone.tenant_id == tenant_id,
            )
        )
        if item is None:
            raise ContractNotFoundError
        if new_status not in MILESTONE_TRANSITIONS[item.status]:
            raise InvalidContractTransitionError
        old_status = item.status
        item.status = new_status
        item.completed_at = datetime.now(UTC) if new_status == MilestoneStatus.COMPLETED else None
        self._record_change(
            tenant_id,
            actor_id,
            contract_id,
            "milestone-status-changed",
            {
                "milestone_id": str(item.id),
                "old_status": old_status.value,
                "new_status": new_status.value,
            },
        )
        await self.session.commit()
        await self.session.refresh(item)
        return item

    async def obligations(
        self, tenant_id: uuid.UUID, contract_id: uuid.UUID
    ) -> list[ContractObligation]:
        await self.get(tenant_id, contract_id)
        return list(
            await self.session.scalars(
                select(ContractObligation)
                .where(
                    ContractObligation.contract_id == contract_id,
                    ContractObligation.tenant_id == tenant_id,
                )
                .order_by(ContractObligation.due_date, ContractObligation.id)
            )
        )

    async def add_obligation(
        self,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        contract_id: uuid.UUID,
        data: ObligationCreate,
    ) -> ContractObligation:
        await self.get(tenant_id, contract_id)
        item = ContractObligation(
            tenant_id=tenant_id,
            contract_id=contract_id,
            status=ObligationStatus.OPEN,
            **data.model_dump(),
        )
        self.session.add(item)
        await self.session.flush()
        self._record_change(
            tenant_id, actor_id, contract_id, "obligation-added", {"obligation_id": str(item.id)}
        )
        await self.session.commit()
        await self.session.refresh(item)
        return item

    async def change_obligation_status(
        self,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        contract_id: uuid.UUID,
        item_id: uuid.UUID,
        new_status: ObligationStatus,
    ) -> ContractObligation:
        item = await self.session.scalar(
            select(ContractObligation).where(
                ContractObligation.id == item_id,
                ContractObligation.contract_id == contract_id,
                ContractObligation.tenant_id == tenant_id,
            )
        )
        if item is None:
            raise ContractNotFoundError
        if new_status not in OBLIGATION_TRANSITIONS[item.status]:
            raise InvalidContractTransitionError
        old_status = item.status
        item.status = new_status
        self._record_change(
            tenant_id,
            actor_id,
            contract_id,
            "obligation-status-changed",
            {
                "obligation_id": str(item.id),
                "old_status": old_status.value,
                "new_status": new_status.value,
            },
        )
        await self.session.commit()
        await self.session.refresh(item)
        return item

    async def payments(
        self, tenant_id: uuid.UUID, contract_id: uuid.UUID
    ) -> list[ContractPayment]:
        await self.get(tenant_id, contract_id)
        return list(
            await self.session.scalars(
                select(ContractPayment)
                .where(
                    ContractPayment.contract_id == contract_id,
                    ContractPayment.tenant_id == tenant_id,
                )
                .order_by(ContractPayment.due_date)
            )
        )

    async def add_payment(
        self,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        contract_id: uuid.UUID,
        data: PaymentCreate,
    ) -> ContractPayment:
        await self.get(tenant_id, contract_id)
        item = ContractPayment(
            tenant_id=tenant_id,
            contract_id=contract_id,
            status=PaymentStatus.PLANNED,
            **data.model_dump(),
        )
        self.session.add(item)
        await self.session.flush()
        self._record_change(
            tenant_id, actor_id, contract_id, "payment-planned", {"payment_id": str(item.id)}
        )
        await self.session.commit()
        await self.session.refresh(item)
        return item

    async def change_payment_status(
        self,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        contract_id: uuid.UUID,
        item_id: uuid.UUID,
        new_status: PaymentStatus,
    ) -> ContractPayment:
        item = await self.session.scalar(
            select(ContractPayment).where(
                ContractPayment.id == item_id,
                ContractPayment.contract_id == contract_id,
                ContractPayment.tenant_id == tenant_id,
            )
        )
        if item is None:
            raise ContractNotFoundError
        if new_status not in PAYMENT_TRANSITIONS[item.status]:
            raise InvalidContractTransitionError
        old_status = item.status
        item.status = new_status
        item.paid_date = date.today() if new_status == PaymentStatus.PAID else None
        self._record_change(
            tenant_id,
            actor_id,
            contract_id,
            "payment-status-changed",
            {
                "payment_id": str(item.id),
                "old_status": old_status.value,
                "new_status": new_status.value,
            },
        )
        await self.session.commit()
        await self.session.refresh(item)
        return item

    def _record_change(
        self,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        contract_id: uuid.UUID,
        action: str,
        payload: dict[str, str],
    ) -> None:
        self.session.add_all(
            [
                ContractAuditEvent(
                    tenant_id=tenant_id,
                    actor_user_id=actor_id,
                    action=action.upper().replace("-", "_"),
                    entity_type="Contract",
                    entity_id=contract_id,
                    payload=payload,
                    request_id=current_request_id(),
                ),
                OutboxEvent(
                    tenant_id=tenant_id,
                    event_type=f"contracts.contract.{action}.v1",
                    aggregate_type="Contract",
                    aggregate_id=contract_id,
                    payload={
                        "contract_id": str(contract_id),
                        "recipient_user_id": str(actor_id),
                        **payload,
                    },
                ),
            ]
        )

    async def audit_events(
        self, tenant_id: uuid.UUID, limit: int, offset: int
    ) -> tuple[list[ContractAuditEvent], int]:
        total = int(
            await self.session.scalar(
                select(func.count())
                .select_from(ContractAuditEvent)
                .where(ContractAuditEvent.tenant_id == tenant_id)
            )
            or 0
        )
        items = list(
            await self.session.scalars(
                select(ContractAuditEvent)
                .where(ContractAuditEvent.tenant_id == tenant_id)
                .order_by(ContractAuditEvent.created_at.desc(), ContractAuditEvent.id)
                .offset(offset)
                .limit(limit)
            )
        )
        return items, total
