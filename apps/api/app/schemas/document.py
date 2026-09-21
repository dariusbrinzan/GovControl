import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class DocumentEntityType(StrEnum):
    LEGAL_CASE = "LegalCase"
    COURT_DECISION = "CourtDecision"
    LEGAL_OBLIGATION = "LegalObligation"
    ENFORCEMENT_PROCEEDING = "EnforcementProceeding"


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    entity_type: DocumentEntityType
    entity_id: uuid.UUID
    category: str
    original_filename: str
    content_type: str
    size_bytes: int
    checksum_sha256: str
    uploaded_by_user_id: uuid.UUID
    created_at: datetime
