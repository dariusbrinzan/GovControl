import uuid
from datetime import date
from decimal import Decimal
from typing import cast

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.legal import (
    CourtDecision,
    EnforcementProceeding,
    EnforcementStatus,
    LegalCase,
    LegalObligation,
    ObligationStatus,
    ObligationStatusHistory,
    PenaltyRule,
)
from app.models.outbox import IntegrationOutboxEvent
from app.repositories.department import DepartmentRepository
from app.repositories.legal import LegalRepository
from app.repositories.user import UserRepository
from app.schemas.legal import (
    CourtDecisionCreate,
    EnforcementProceedingCreate,
    LegalCaseCreate,
    LegalObligationCreate,
    PenaltyRuleCreate,
)
from app.services.audit import AuditService
from app.services.deadlines import DeadlineState, deadline_state
from app.services.penalties import PenaltyCalculationType, calculate_penalty_exposure


class LegalConflictError(Exception):
    pass


class LegalResourceNotFoundError(Exception):
    pass


class InvalidStatusTransitionError(Exception):
    pass


ALLOWED_TRANSITIONS: dict[ObligationStatus, set[ObligationStatus]] = {
    ObligationStatus.DRAFT: {ObligationStatus.OPEN, ObligationStatus.CANCELLED},
    ObligationStatus.OPEN: {
        ObligationStatus.IN_PROGRESS,
        ObligationStatus.AT_RISK,
        ObligationStatus.OVERDUE,
        ObligationStatus.CANCELLED,
    },
    ObligationStatus.IN_PROGRESS: {
        ObligationStatus.AT_RISK,
        ObligationStatus.OVERDUE,
        ObligationStatus.COMPLETED,
        ObligationStatus.CANCELLED,
    },
    ObligationStatus.AT_RISK: {
        ObligationStatus.IN_PROGRESS,
        ObligationStatus.OVERDUE,
        ObligationStatus.COMPLETED,
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


class LegalService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = LegalRepository(session)
        self.audit = AuditService(session)
        self.departments = DepartmentRepository(session)
        self.users = UserRepository(session)

    async def create_case(
        self, tenant_id: uuid.UUID, actor_id: uuid.UUID, data: LegalCaseCreate
    ) -> LegalCase:
        item = LegalCase(tenant_id=tenant_id, **data.model_dump())
        self.session.add(item)
        return cast(
            LegalCase,
            await self._save_created(
                item, tenant_id, actor_id, "LegalCase", {"case_number": item.case_number}
            ),
        )

    async def list_cases(self, tenant_id: uuid.UUID, limit: int = 100) -> list[LegalCase]:
        return await self.repo.cases(tenant_id, limit)

    async def get_case(self, tenant_id: uuid.UUID, case_id: uuid.UUID) -> LegalCase:
        item = await self.repo.case(case_id, tenant_id)
        if item is None:
            raise LegalResourceNotFoundError
        return item

    async def list_decisions(
        self, tenant_id: uuid.UUID, limit: int = 100, case_id: uuid.UUID | None = None
    ) -> list[CourtDecision]:
        if case_id is not None and await self.repo.case(case_id, tenant_id) is None:
            raise LegalResourceNotFoundError
        return await self.repo.decisions(tenant_id, limit, case_id)

    async def create_enforcement(
        self, tenant_id: uuid.UUID, actor_id: uuid.UUID, data: EnforcementProceedingCreate
    ) -> EnforcementProceeding:
        if await self.repo.obligation(data.obligation_id, tenant_id) is None:
            raise LegalResourceNotFoundError
        item = EnforcementProceeding(tenant_id=tenant_id, **data.model_dump())
        self.session.add(item)
        return cast(
            EnforcementProceeding,
            await self._save_created(
                item,
                tenant_id,
                actor_id,
                "EnforcementProceeding",
                {"file_number": item.file_number},
            ),
        )

    async def list_enforcements(
        self, tenant_id: uuid.UUID, limit: int = 100
    ) -> list[EnforcementProceeding]:
        return await self.repo.enforcements(tenant_id, limit)

    async def change_enforcement_status(
        self,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        enforcement_id: uuid.UUID,
        new_status: EnforcementStatus,
    ) -> EnforcementProceeding:
        item = await self.repo.enforcement(enforcement_id, tenant_id)
        if item is None:
            raise LegalResourceNotFoundError
        old_status = item.status
        item.status = new_status
        self.audit.record_event(
            tenant_id=tenant_id,
            actor_user_id=actor_id,
            action="STATUS_CHANGED",
            entity_type="EnforcementProceeding",
            entity_id=item.id,
            new_value={"old_status": old_status.value, "new_status": new_status.value},
        )
        self._event(
            tenant_id,
            actor_id,
            "legal.enforcement.updated.v1",
            "EnforcementProceeding",
            item.id,
        )
        await self.session.commit()
        await self.session.refresh(item)
        return item

    async def create_penalty_rule(
        self, tenant_id: uuid.UUID, actor_id: uuid.UUID, data: PenaltyRuleCreate
    ) -> PenaltyRule:
        if await self.repo.obligation(data.obligation_id, tenant_id) is None:
            raise LegalResourceNotFoundError
        values = data.model_dump()
        calculate_penalty_exposure(as_of_date=data.start_date, **values)
        item = PenaltyRule(tenant_id=tenant_id, **values)
        self.session.add(item)
        return cast(
            PenaltyRule,
            await self._save_created(
                item,
                tenant_id,
                actor_id,
                "PenaltyRule",
                {"calculation_type": item.calculation_type, "start_date": str(item.start_date)},
            ),
        )

    async def list_penalty_rules(self, tenant_id: uuid.UUID, limit: int = 100) -> list[PenaltyRule]:
        return await self.repo.penalty_rules(tenant_id, limit)

    async def penalty_exposure(
        self, tenant_id: uuid.UUID, rule_id: uuid.UUID, as_of_date: date
    ) -> tuple[PenaltyRule, Decimal]:
        item = await self.repo.penalty_rule(rule_id, tenant_id)
        if item is None:
            raise LegalResourceNotFoundError
        return (
            item,
            calculate_penalty_exposure(
                calculation_type=PenaltyCalculationType(item.calculation_type),
                start_date=item.start_date,
                as_of_date=as_of_date,
                daily_amount=item.daily_amount,
                percentage=item.percentage,
                base_value=item.base_value,
                end_date=item.end_date,
            ),
        )

    async def create_decision(
        self,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        case_id: uuid.UUID,
        data: CourtDecisionCreate,
    ) -> CourtDecision:
        if await self.repo.case(case_id, tenant_id) is None:
            raise LegalResourceNotFoundError
        item = CourtDecision(tenant_id=tenant_id, case_id=case_id, **data.model_dump())
        self.session.add(item)
        return cast(
            CourtDecision,
            await self._save_created(
                item,
                tenant_id,
                actor_id,
                "CourtDecision",
                {"decision_number": item.decision_number},
            ),
        )

    async def create_obligation(
        self, tenant_id: uuid.UUID, actor_id: uuid.UUID, data: LegalObligationCreate
    ) -> LegalObligation:
        if await self.repo.decision(data.court_decision_id, tenant_id) is None:
            raise LegalResourceNotFoundError
        if (
            data.responsible_department_id
            and await self.departments.get_by_id_for_tenant(
                data.responsible_department_id, tenant_id
            )
            is None
        ):
            raise LegalResourceNotFoundError
        if (
            data.responsible_user_id
            and await self.users.get_by_id_for_tenant(data.responsible_user_id, tenant_id) is None
        ):
            raise LegalResourceNotFoundError
        item = LegalObligation(tenant_id=tenant_id, **data.model_dump())
        self.session.add(item)
        return cast(
            LegalObligation,
            await self._save_created(
                item,
                tenant_id,
                actor_id,
                "LegalObligation",
                {
                    "due_date": str(item.due_date) if item.due_date else None,
                    "status": item.status.value,
                },
            ),
        )

    async def list_obligations(
        self, tenant_id: uuid.UUID, limit: int = 500
    ) -> list[LegalObligation]:
        return await self.repo.obligations(tenant_id, limit)

    async def get_obligation(
        self, tenant_id: uuid.UUID, obligation_id: uuid.UUID
    ) -> LegalObligation:
        item = await self.repo.obligation(obligation_id, tenant_id)
        if item is None:
            raise LegalResourceNotFoundError
        return item

    async def overdue_obligations(self, tenant_id: uuid.UUID, today: date) -> list[LegalObligation]:
        return [
            item
            for item in await self.list_obligations(tenant_id)
            if deadline_state(item.due_date, item.status, today) == DeadlineState.OVERDUE
        ]

    async def dashboard(self, tenant_id: uuid.UUID, today: date) -> dict[str, int]:
        return await self.repo.dashboard_counts(tenant_id, today)

    async def change_status(
        self,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        obligation_id: uuid.UUID,
        new_status: ObligationStatus,
    ) -> LegalObligation:
        item = await self.repo.obligation(obligation_id, tenant_id)
        if item is None:
            raise LegalResourceNotFoundError
        if new_status not in ALLOWED_TRANSITIONS[item.status]:
            raise InvalidStatusTransitionError
        old_status = item.status
        item.status = new_status
        item.completion_date = date.today() if new_status == ObligationStatus.COMPLETED else None
        self.session.add(
            ObligationStatusHistory(
                tenant_id=tenant_id,
                obligation_id=item.id,
                old_status=old_status,
                new_status=new_status,
                actor_user_id=actor_id,
            )
        )
        self.audit.record_event(
            tenant_id=tenant_id,
            actor_user_id=actor_id,
            action="STATUS_CHANGED",
            entity_type="LegalObligation",
            entity_id=item.id,
            new_value={"old_status": old_status.value, "new_status": new_status.value},
        )
        await self.session.commit()
        await self.session.refresh(item)
        return item

    async def _save_created(
        self,
        item: LegalCase | CourtDecision | LegalObligation | EnforcementProceeding | PenaltyRule,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        entity_type: str,
        value: dict[str, str | None],
    ) -> LegalCase | CourtDecision | LegalObligation | EnforcementProceeding | PenaltyRule:
        try:
            await self.session.flush()
            self.audit.record_created(
                tenant_id=tenant_id,
                actor_user_id=actor_id,
                entity_type=entity_type,
                entity_id=item.id,
                new_value=value,
            )
            event_type = {
                "EnforcementProceeding": "legal.enforcement.updated.v1",
                "PenaltyRule": "legal.penalty.exposure.v1",
            }.get(entity_type)
            if event_type is not None:
                self._event(tenant_id, actor_id, event_type, entity_type, item.id)
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise LegalConflictError from exc
        await self.session.refresh(item)
        return item

    def _event(
        self,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        event_type: str,
        aggregate_type: str,
        aggregate_id: uuid.UUID,
    ) -> None:
        self.session.add(
            IntegrationOutboxEvent(
                tenant_id=tenant_id,
                event_type=event_type,
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                payload={"recipient_user_id": str(actor_id)},
            )
        )
