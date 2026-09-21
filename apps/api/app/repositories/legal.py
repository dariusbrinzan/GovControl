import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.legal import (
    CourtDecision,
    EnforcementProceeding,
    LegalCase,
    LegalObligation,
    PenaltyRule,
)


class LegalRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def case(self, item_id: uuid.UUID, tenant_id: uuid.UUID) -> LegalCase | None:
        item: LegalCase | None = await self.session.scalar(
            select(LegalCase).where(LegalCase.id == item_id, LegalCase.tenant_id == tenant_id)
        )
        return item

    async def decision(self, item_id: uuid.UUID, tenant_id: uuid.UUID) -> CourtDecision | None:
        item: CourtDecision | None = await self.session.scalar(
            select(CourtDecision).where(
                CourtDecision.id == item_id, CourtDecision.tenant_id == tenant_id
            )
        )
        return item

    async def obligation(self, item_id: uuid.UUID, tenant_id: uuid.UUID) -> LegalObligation | None:
        item: LegalObligation | None = await self.session.scalar(
            select(LegalObligation).where(
                LegalObligation.id == item_id, LegalObligation.tenant_id == tenant_id
            )
        )
        return item

    async def enforcement(
        self, item_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> EnforcementProceeding | None:
        item: EnforcementProceeding | None = await self.session.scalar(
            select(EnforcementProceeding).where(
                EnforcementProceeding.id == item_id,
                EnforcementProceeding.tenant_id == tenant_id,
            )
        )
        return item

    async def penalty_rule(self, item_id: uuid.UUID, tenant_id: uuid.UUID) -> PenaltyRule | None:
        item: PenaltyRule | None = await self.session.scalar(
            select(PenaltyRule).where(PenaltyRule.id == item_id, PenaltyRule.tenant_id == tenant_id)
        )
        return item

    async def cases(self, tenant_id: uuid.UUID) -> list[LegalCase]:
        return list(
            await self.session.scalars(
                select(LegalCase)
                .where(LegalCase.tenant_id == tenant_id)
                .order_by(LegalCase.created_at.desc())
            )
        )

    async def decisions(
        self, tenant_id: uuid.UUID, case_id: uuid.UUID | None = None
    ) -> list[CourtDecision]:
        statement = select(CourtDecision).where(CourtDecision.tenant_id == tenant_id)
        if case_id is not None:
            statement = statement.where(CourtDecision.case_id == case_id)
        return list(
            await self.session.scalars(
                statement.order_by(CourtDecision.decision_date.desc(), CourtDecision.id)
            )
        )

    async def obligations(self, tenant_id: uuid.UUID) -> list[LegalObligation]:
        return list(
            await self.session.scalars(
                select(LegalObligation)
                .where(LegalObligation.tenant_id == tenant_id)
                .order_by(LegalObligation.due_date, LegalObligation.id)
            )
        )

    async def enforcements(self, tenant_id: uuid.UUID) -> list[EnforcementProceeding]:
        return list(
            await self.session.scalars(
                select(EnforcementProceeding)
                .where(EnforcementProceeding.tenant_id == tenant_id)
                .order_by(EnforcementProceeding.start_date.desc())
            )
        )

    async def penalty_rules(self, tenant_id: uuid.UUID) -> list[PenaltyRule]:
        return list(
            await self.session.scalars(
                select(PenaltyRule)
                .where(PenaltyRule.tenant_id == tenant_id)
                .order_by(PenaltyRule.start_date.desc(), PenaltyRule.id)
            )
        )
