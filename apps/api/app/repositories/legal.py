import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.legal import CourtDecision, LegalCase, LegalObligation


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

    async def cases(self, tenant_id: uuid.UUID) -> list[LegalCase]:
        return list(
            await self.session.scalars(
                select(LegalCase)
                .where(LegalCase.tenant_id == tenant_id)
                .order_by(LegalCase.created_at.desc())
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
