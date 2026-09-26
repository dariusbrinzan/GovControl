import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from documents_app.models import DocumentState, ResourceType


class UserContext(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    department_id: uuid.UUID | None
    email: str
    display_name: str
    roles: list[str]
    permissions: list[str]


class DocumentLinkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    resource_type: ResourceType
    resource_id: uuid.UUID
    created_at: datetime


class DocumentVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    version_number: int
    original_filename: str
    safe_filename: str
    content_type: str
    size_bytes: int
    checksum_sha256: str
    state: DocumentState
    rejection_reason: str | None
    created_by_user_id: uuid.UUID
    created_at: datetime
    scanned_at: datetime | None


class DocumentResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    category: str
    classification: str
    retention_until: date | None
    state: DocumentState
    current_version_number: int
    lock_version: int
    created_by_user_id: uuid.UUID
    archived_at: datetime | None
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime
    current_version: DocumentVersionResponse
    links: list[DocumentLinkResponse]


class DocumentPage(BaseModel):
    items: list[DocumentResponse]
    total: int
    page: int
    page_size: int


class DocumentMetadataUpdate(BaseModel):
    category: str | None = Field(None, min_length=1, max_length=100)
    classification: str | None = Field(None, min_length=1, max_length=50)
    retention_until: date | None = None


class DocumentLinkCreate(BaseModel):
    resource_type: ResourceType
    resource_id: uuid.UUID


class AuditEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    actor_user_id: uuid.UUID
    action: str
    request_id: uuid.UUID | None
    payload: dict[str, object] | None
    created_at: datetime
