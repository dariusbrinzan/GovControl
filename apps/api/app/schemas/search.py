import uuid
from datetime import date

from pydantic import BaseModel


class LegalSearchResult(BaseModel):
    id: uuid.UUID
    entity_type: str
    title: str
    summary: str
    status: str
    due_date: date | None = None


class LegalSearchResponse(BaseModel):
    results: list[LegalSearchResult]
