import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.legal import LegalCase, LegalObligation


async def search_legal(
    session: AsyncSession, tenant_id: uuid.UUID, query: str, limit: int
) -> tuple[list[LegalCase], list[LegalObligation]]:
    pattern = f"%{query.strip()}%"
    cases = list(
        await session.scalars(
            select(LegalCase).where(
                LegalCase.tenant_id == tenant_id,
                func.concat(LegalCase.case_number, " ", LegalCase.subject).ilike(pattern),
            ).order_by(LegalCase.created_at.desc()).limit(limit)
        )
    )
    obligations = list(
        await session.scalars(
            select(LegalObligation).where(
                LegalObligation.tenant_id == tenant_id, LegalObligation.description.ilike(pattern)
            ).order_by(LegalObligation.due_date, LegalObligation.id).limit(limit)
        )
    )
    return cases, obligations
