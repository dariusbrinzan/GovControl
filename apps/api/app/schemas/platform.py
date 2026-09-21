import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, StringConstraints, field_validator

from app.models.rbac import RoleScope

DepartmentName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)
]
DepartmentCode = Annotated[str, StringConstraints(strip_whitespace=True, max_length=64)]
DisplayName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]


class TenantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    is_active: bool


class DepartmentCreate(BaseModel):
    name: DepartmentName
    code: DepartmentCode | None = None
    parent_department_id: uuid.UUID | None = None

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized_value = value.upper()
        return normalized_value or None


class DepartmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    parent_department_id: uuid.UUID | None
    name: str
    code: str | None
    created_at: datetime
    updated_at: datetime


class RoleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID | None
    scope: RoleScope
    key: str
    name: str
    description: str | None


class UserCreate(BaseModel):
    email: EmailStr
    display_name: DisplayName
    department_id: uuid.UUID | None = None

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).lower()


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    department_id: uuid.UUID | None
    email: str
    display_name: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class UserRoleAssign(BaseModel):
    role_id: uuid.UUID
