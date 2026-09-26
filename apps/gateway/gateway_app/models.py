from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class UserContext(BaseModel):
    id: str
    tenant_id: str
    department_id: str | None
    email: str = Field(min_length=3, max_length=320)
    display_name: str
    roles: list[str]
    permissions: list[str]


class SessionRecord(BaseModel):
    id: str
    user: UserContext
    auth_method: Literal["local", "oidc"]
    created_at: datetime
    rotated_at: datetime
    expires_at: datetime
    csrf_token: str
    oidc_issuer: str | None = None
    oidc_subject: str | None = None


class SessionResponse(BaseModel):
    user: UserContext
    csrf_token: str
    expires_at: datetime
    auth_method: Literal["local", "oidc"]


class OIDCIdentity(BaseModel):
    issuer: str = Field(min_length=1, max_length=2048)
    subject: str = Field(min_length=1, max_length=255)
    email: EmailStr
    email_verified: bool
    display_name: str | None = Field(None, max_length=255)
