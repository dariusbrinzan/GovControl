import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from contracts_app.models import (
    ContractStatus,
    MilestoneStatus,
    ObligationStatus,
    PaymentStatus,
)

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class UserContext(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    department_id: uuid.UUID | None
    email: str
    display_name: str
    roles: list[str]
    permissions: list[str]
    authorization: str = Field(default="", exclude=True, repr=False)


class ContractCreate(BaseModel):
    contract_number: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
    ]
    title: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
    ]
    description: str | None = None
    value: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    currency: str = "RON"
    signed_date: date | None = None
    start_date: date
    end_date: date
    responsible_department_id: uuid.UUID | None = None
    responsible_user_id: uuid.UUID | None = None

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        value = value.strip().upper()
        if len(value) != 3 or not value.isalpha():
            raise ValueError("currency must be a three-letter ISO code")
        return value

    @model_validator(mode="after")
    def validate_dates(self) -> "ContractCreate":
        if self.end_date < self.start_date:
            raise ValueError("end_date must not be before start_date")
        if self.signed_date is not None and self.signed_date > self.end_date:
            raise ValueError("signed_date must not be after end_date")
        return self


class ContractStatusChange(BaseModel):
    status: ContractStatus


class ContractUpdate(BaseModel):
    title: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
    ] | None = None
    description: str | None = None
    value: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=2)
    currency: str | None = None
    signed_date: date | None = None
    start_date: date | None = None
    end_date: date | None = None
    responsible_department_id: uuid.UUID | None = None
    responsible_user_id: uuid.UUID | None = None

    @field_validator("currency")
    @classmethod
    def normalize_optional_currency(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip().upper()
        if len(value) != 3 or not value.isalpha():
            raise ValueError("currency must be a three-letter ISO code")
        return value


class ContractResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    tenant_id: uuid.UUID
    contract_number: str
    title: str
    description: str | None
    value: Decimal
    currency: str
    signed_date: date | None
    start_date: date
    end_date: date
    status: ContractStatus
    responsible_department_id: uuid.UUID | None
    responsible_user_id: uuid.UUID | None
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime


class ContractPage(BaseModel):
    items: list[ContractResponse]
    total: int
    limit: int
    offset: int


class ContractDashboard(BaseModel):
    total_contracts: int
    active_contracts: int
    expiring_within_30_days: int
    status_counts: dict[str, int]
    active_value_by_currency: dict[str, Decimal]


class PartyCreate(BaseModel):
    name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
    ]
    registration_number: str | None = None
    party_type: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)
    ]
    role: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
    email: str | None = None
    phone: str | None = None
    address: str | None = None


class PartyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    registration_number: str | None
    party_type: str
    email: str | None
    phone: str | None
    address: str | None
    role: str | None = None


class AmendmentCreate(BaseModel):
    amendment_number: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
    ]
    signed_date: date
    value_change: Decimal | None = Field(default=None, max_digits=18, decimal_places=2)
    end_date_change: date | None = None
    description: NonEmptyText


class AmendmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    tenant_id: uuid.UUID
    contract_id: uuid.UUID
    amendment_number: str
    signed_date: date
    value_change: Decimal | None
    end_date_change: date | None
    description: str
    created_at: datetime


class MilestoneCreate(BaseModel):
    title: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
    ]
    due_date: date


class MilestoneResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    tenant_id: uuid.UUID
    contract_id: uuid.UUID
    title: str
    due_date: date
    status: MilestoneStatus
    completed_at: datetime | None


class MilestoneStatusChange(BaseModel):
    status: MilestoneStatus


class ObligationCreate(BaseModel):
    description: NonEmptyText
    due_date: date | None = None
    responsible_user_id: uuid.UUID | None = None


class ObligationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    tenant_id: uuid.UUID
    contract_id: uuid.UUID
    description: str
    due_date: date | None
    status: ObligationStatus
    responsible_user_id: uuid.UUID | None


class ObligationStatusChange(BaseModel):
    status: ObligationStatus


class PaymentCreate(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    currency: str = "RON"
    due_date: date
    reference: str | None = None

    @field_validator("currency")
    @classmethod
    def normalize_payment_currency(cls, value: str) -> str:
        value = value.strip().upper()
        if len(value) != 3 or not value.isalpha():
            raise ValueError("currency must be a three-letter ISO code")
        return value


class PaymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    tenant_id: uuid.UUID
    contract_id: uuid.UUID
    amount: Decimal
    currency: str
    due_date: date
    paid_date: date | None
    status: PaymentStatus
    reference: str | None


class PaymentStatusChange(BaseModel):
    status: PaymentStatus


class ContractDetailResponse(BaseModel):
    contract: ContractResponse
    parties: list[PartyResponse]
    amendments: list[AmendmentResponse]
    milestones: list[MilestoneResponse]
    obligations: list[ObligationResponse]
    payments: list[PaymentResponse]


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    tenant_id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    notification_type: str
    title: str
    body: str
    due_date: date | None
    read_at: datetime | None
    created_at: datetime


class AuditEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    tenant_id: uuid.UUID
    actor_user_id: uuid.UUID
    action: str
    entity_type: str
    entity_id: uuid.UUID
    payload: dict[str, Any] | None
    request_id: uuid.UUID | None
    created_at: datetime


class AuditEventPage(BaseModel):
    items: list[AuditEventResponse]
    total: int
    limit: int
    offset: int
