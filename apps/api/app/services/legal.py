import uuid
from datetime import date
from typing import cast

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.legal import (
    CourtDecision,
    LegalCase,
    LegalObligation,
    ObligationStatus,
    ObligationStatusHistory,
)
from app.repositories.department import DepartmentRepository
from app.repositories.legal import LegalRepository
from app.repositories.user import UserRepository
from app.schemas.legal import CourtDecisionCreate, LegalCaseCreate, LegalObligationCreate
from app.services.audit import AuditService
from app.services.deadlines import DeadlineState, deadline_state


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

    async def list_cases(self, tenant_id: uuid.UUID) -> list[LegalCase]:
        return await self.repo.cases(tenant_id)

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

    async def list_obligations(self, tenant_id: uuid.UUID) -> list[LegalObligation]:
        return await self.repo.obligations(tenant_id)

    async def overdue_obligations(self, tenant_id: uuid.UUID, today: date) -> list[LegalObligation]:
        return [
            item
            for item in await self.list_obligations(tenant_id)
            if deadline_state(item.due_date, item.status, today) == DeadlineState.OVERDUE
        ]

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
        item: LegalCase | CourtDecision | LegalObligation,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        entity_type: str,
        value: dict[str, str | None],
    ) -> LegalCase | CourtDecision | LegalObligation:
        try:
            await self.session.flush()
            self.audit.record_created(
                tenant_id=tenant_id,
                actor_user_id=actor_id,
                entity_type=entity_type,
                entity_id=item.id,
                new_value=value,
            )
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise LegalConflictError from exc
        await self.session.refresh(item)
        return item
