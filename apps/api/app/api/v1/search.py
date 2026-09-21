from fastapi import APIRouter, Query

from app.core.security import CurrentUserDependency, SessionDependency
from app.schemas.search import LegalSearchResponse, LegalSearchResult
from app.services.search import search_legal

router = APIRouter(prefix="/search")


@router.get("/legal", response_model=LegalSearchResponse)
async def legal_search(
    current_user: CurrentUserDependency,
    session: SessionDependency,
    q: str = Query(min_length=2, max_length=100),
) -> LegalSearchResponse:
    cases, obligations = await search_legal(session, current_user.tenant_id, q)
    results = [
        LegalSearchResult(
            id=item.id,
            entity_type="LegalCase",
            title=item.case_number,
            summary=item.subject,
            status=item.status.value,
        )
        for item in cases
    ]
    results.extend(
        LegalSearchResult(
            id=item.id,
            entity_type="LegalObligation",
            title=item.description[:120],
            summary=item.description,
            status=item.status.value,
            due_date=item.due_date,
        )
        for item in obligations
    )
    return LegalSearchResponse(results=results)
