import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from contracts_app.models import ContractStatus

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class UserContext(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    department_id: uuid.UUID | None
    email: str
    display_name: str
    roles: list[str]
    permissions: list[str]


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


class ContractDashboard(BaseModel):
    total_contracts: int
    active_contracts: int
    expiring_within_30_days: int
    total_active_value: Decimal
