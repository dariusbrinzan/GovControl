import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.legal import LegalCase, LegalObligation


async def search_legal(
    session: AsyncSession, tenant_id: uuid.UUID, query: str
) -> tuple[list[LegalCase], list[LegalObligation]]:
    pattern = f"%{query.strip()}%"
    cases = list(
        await session.scalars(
            select(LegalCase).where(
                LegalCase.tenant_id == tenant_id,
                or_(LegalCase.case_number.ilike(pattern), LegalCase.subject.ilike(pattern)),
            )
        )
    )
    obligations = list(
        await session.scalars(
            select(LegalObligation).where(
                LegalObligation.tenant_id == tenant_id, LegalObligation.description.ilike(pattern)
            )
        )
    )
    return cases, obligations
