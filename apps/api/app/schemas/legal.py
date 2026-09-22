import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator

from app.models.legal import EnforcementStatus, LegalCaseStatus, ObligationStatus, ObligationType
from app.services.penalties import PenaltyCalculationType

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


class EnforcementProceedingCreate(BaseModel):
    obligation_id: uuid.UUID
    file_number: ShortText
    enforcement_officer: ShortText | None = None
    start_date: date


class EnforcementProceedingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    tenant_id: uuid.UUID
    obligation_id: uuid.UUID
    file_number: str
    enforcement_officer: str | None
    start_date: date
    status: EnforcementStatus


class EnforcementStatusChange(BaseModel):
    status: EnforcementStatus


class PenaltyRuleCreate(BaseModel):
    obligation_id: uuid.UUID
    calculation_type: PenaltyCalculationType
    daily_amount: Decimal | None = None
    percentage: Decimal | None = None
    base_value: Decimal | None = None
    start_date: date
    end_date: date | None = None

    @model_validator(mode="after")
    def validate_calculation(self) -> "PenaltyRuleCreate":
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("end_date must not be before start_date")
        if self.calculation_type == PenaltyCalculationType.DAILY_AMOUNT:
            if self.daily_amount is None or self.daily_amount <= 0:
                raise ValueError("daily_amount must be greater than zero for DAILY_AMOUNT")
            if self.percentage is not None or self.base_value is not None:
                raise ValueError("percentage and base_value only apply to PERCENTAGE_OF_BASE")
        elif (
            self.percentage is None
            or self.percentage <= 0
            or self.base_value is None
            or self.base_value <= 0
        ):
            raise ValueError("positive percentage and base_value are required")
        return self


class PenaltyRuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    tenant_id: uuid.UUID
    obligation_id: uuid.UUID
    calculation_type: PenaltyCalculationType
    daily_amount: Decimal | None
    percentage: Decimal | None
    base_value: Decimal | None
    start_date: date
    end_date: date | None


class PenaltyExposureResponse(BaseModel):
    rule_id: uuid.UUID
    as_of_date: date
    amount: Decimal
