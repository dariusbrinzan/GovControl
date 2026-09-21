from fastapi import APIRouter, Query

from app.core.security import CurrentUserDependency, SessionDependency
from app.services.search import search_legal

router = APIRouter(prefix="/search")


@router.get("/legal")
async def legal_search(
    current_user: CurrentUserDependency,
    session: SessionDependency,
    q: str = Query(min_length=2, max_length=100),
) -> dict[str, list[str]]:
    cases, obligations = await search_legal(session, current_user.tenant_id, q)
    return {
        "case_ids": [str(item.id) for item in cases],
        "obligation_ids": [str(item.id) for item in obligations],
    }
