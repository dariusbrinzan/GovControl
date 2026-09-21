import uuid
from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

from app.models.legal import LegalCaseStatus, ObligationStatus, ObligationType

ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
LongText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class LegalCaseCreate(BaseModel):
    case_number: ShortText
    court: ShortText
    subject: LongText
    filing_date: date | None = None
    external_reference: ShortText | None = None


class LegalCaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    tenant_id: uuid.UUID
    case_number: str
    court: str
    subject: str
    filing_date: date | None
    status: LegalCaseStatus
    external_reference: str | None
    created_at: datetime
    updated_at: datetime


class CourtDecisionCreate(BaseModel):
    decision_number: ShortText
    decision_date: date
    final_date: date | None = None
    decision_type: ShortText
    summary: str | None = None


class CourtDecisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    tenant_id: uuid.UUID
    case_id: uuid.UUID
    decision_number: str
    decision_date: date
    final_date: date | None
    decision_type: str
    summary: str | None
    created_at: datetime


class LegalObligationCreate(BaseModel):
    court_decision_id: uuid.UUID
    obligation_type: ObligationType
    description: LongText
    responsible_department_id: uuid.UUID | None = None
    responsible_user_id: uuid.UUID | None = None
    due_date: date | None = None


class ObligationStatusChange(BaseModel):
    status: ObligationStatus


class LegalObligationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    tenant_id: uuid.UUID
    court_decision_id: uuid.UUID
    obligation_type: ObligationType
    description: str
    responsible_department_id: uuid.UUID | None
    responsible_user_id: uuid.UUID | None
    due_date: date | None
    status: ObligationStatus
    completion_date: date | None
    created_at: datetime
    updated_at: datetime
