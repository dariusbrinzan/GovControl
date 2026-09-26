import unicodedata
import uuid
from datetime import date
from typing import Annotated
from urllib.parse import quote

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from documents_app.config import Settings, get_settings
from documents_app.database import get_session
from documents_app.models import DocumentState, DocumentVersion, ResourceType
from documents_app.resources import validate_resource
from documents_app.schemas import (
    AuditEventResponse,
    DocumentLinkCreate,
    DocumentMetadataUpdate,
    DocumentPage,
    DocumentResponse,
    DocumentVersionResponse,
    UserContext,
)
from documents_app.security import require_permission
from documents_app.service import (
    DocumentConflictError,
    DocumentNotFoundError,
    DocumentService,
    DocumentUnavailableError,
)
from documents_app.storage import S3Storage, StorageError

router = APIRouter(prefix="/documents", tags=["documents"])
Session = Annotated[AsyncSession, Depends(get_session)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]
Reader = Annotated[UserContext, Depends(require_permission("documents.read"))]
Uploader = Annotated[UserContext, Depends(require_permission("documents.upload"))]
Manager = Annotated[UserContext, Depends(require_permission("documents.manage"))]
Deleter = Annotated[UserContext, Depends(require_permission("documents.delete"))]
Auditor = Annotated[UserContext, Depends(require_permission("documents.audit"))]
Authorization = Annotated[str, Header(alias="Authorization")]


def service(request: Request, session: Session, settings: SettingsDependency) -> DocumentService:
    return DocumentService(session, request.app.state.storage, settings)


Service = Annotated[DocumentService, Depends(service)]


def etag(lock_version: int) -> str:
    return f'"{lock_version}"'


def content_disposition(filename: str) -> str:
    ascii_name = (
        unicodedata.normalize("NFKD", filename).encode("ascii", "ignore").decode().strip()
        or "document"
    )
    ascii_name = ascii_name.replace('"', "_")
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"


def parse_if_match(value: str | None) -> int:
    if value is None:
        raise HTTPException(status.HTTP_428_PRECONDITION_REQUIRED, "If-Match is required.")
    normalized = value.removeprefix("W/").strip().strip('"')
    try:
        return int(normalized)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid If-Match value.") from exc


def service_error(exc: Exception) -> HTTPException:
    if isinstance(exc, DocumentNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, "Document not found in this tenant.")
    if isinstance(exc, DocumentConflictError):
        return HTTPException(status.HTTP_409_CONFLICT, str(exc))
    if isinstance(exc, DocumentUnavailableError):
        return HTTPException(status.HTTP_423_LOCKED, "Document is not available for download.")
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Document storage is unavailable.")


@router.get("", response_model=DocumentPage)
async def list_documents(
    request: Request,
    user: Reader,
    documents: Service,
    settings: SettingsDependency,
    authorization: Authorization,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
    query: Annotated[str | None, Query(max_length=200)] = None,
    state: DocumentState | None = None,
    resource_type: ResourceType | None = None,
    resource_id: uuid.UUID | None = None,
    include_deleted: bool = False,
) -> DocumentPage:
    if resource_type is not None and resource_id is not None:
        await validate_resource(
            request, settings, authorization, user.tenant_id, resource_type, resource_id
        )
    try:
        items, total = await documents.list(
            user.tenant_id,
            page=page,
            page_size=page_size,
            query=query,
            state=state,
            resource_type=resource_type,
            resource_id=resource_id,
            include_deleted=include_deleted,
        )
    except (DocumentNotFoundError, DocumentConflictError, DocumentUnavailableError) as exc:
        raise service_error(exc) from exc
    return DocumentPage(items=items, total=total, page=page, page_size=page_size)


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    request: Request,
    response: Response,
    resource_type: Annotated[ResourceType, Form()],
    resource_id: Annotated[uuid.UUID, Form()],
    category: Annotated[str, Form(min_length=1, max_length=100)],
    file: Annotated[UploadFile, File()],
    user: Uploader,
    documents: Service,
    settings: SettingsDependency,
    authorization: Authorization,
    classification: Annotated[str, Form(min_length=1, max_length=50)] = "INTERNAL",
    retention_until: Annotated[date | None, Form()] = None,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key", max_length=200)] = None,
) -> DocumentResponse:
    await validate_resource(
        request, settings, authorization, user.tenant_id, resource_type, resource_id
    )
    try:
        result = await documents.create(
            tenant_id=user.tenant_id,
            actor_id=user.id,
            resource_type=resource_type,
            resource_id=resource_id,
            category=category,
            classification=classification,
            retention_until=retention_until,
            upload=file,
            idempotency_key=idempotency_key,
        )
    except (
        DocumentConflictError,
        DocumentNotFoundError,
        DocumentUnavailableError,
        StorageError,
    ) as exc:
        raise service_error(exc) from exc
    response.headers["ETag"] = etag(result.lock_version)
    return result


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: uuid.UUID,
    response: Response,
    user: Reader,
    documents: Service,
) -> DocumentResponse:
    try:
        result = await documents.get(user.tenant_id, document_id)
    except (DocumentNotFoundError, DocumentUnavailableError) as exc:
        raise service_error(exc) from exc
    response.headers["ETag"] = etag(result.lock_version)
    return result


@router.get("/{document_id}/versions", response_model=list[DocumentVersionResponse])
async def document_versions(
    document_id: uuid.UUID,
    user: Reader,
    session: Session,
    documents: Service,
) -> list[DocumentVersionResponse]:
    try:
        await documents.get(user.tenant_id, document_id)
    except (DocumentNotFoundError, DocumentUnavailableError) as exc:
        raise service_error(exc) from exc
    versions = list(
        await session.scalars(
            select(DocumentVersion)
            .where(
                DocumentVersion.tenant_id == user.tenant_id,
                DocumentVersion.document_id == document_id,
            )
            .order_by(DocumentVersion.version_number.desc())
        )
    )
    return [DocumentVersionResponse.model_validate(item) for item in versions]


@router.post("/{document_id}/versions", response_model=DocumentResponse)
async def add_version(
    document_id: uuid.UUID,
    response: Response,
    file: Annotated[UploadFile, File()],
    user: Uploader,
    documents: Service,
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> DocumentResponse:
    try:
        result = await documents.add_version(
            tenant_id=user.tenant_id,
            document_id=document_id,
            actor_id=user.id,
            expected_version=parse_if_match(if_match),
            upload=file,
        )
    except (
        DocumentConflictError,
        DocumentNotFoundError,
        DocumentUnavailableError,
        StorageError,
    ) as exc:
        raise service_error(exc) from exc
    response.headers["ETag"] = etag(result.lock_version)
    return result


@router.get("/{document_id}/download")
async def download_document(
    document_id: uuid.UUID,
    request: Request,
    user: Reader,
    documents: Service,
    version: Annotated[int | None, Query(ge=1)] = None,
) -> StreamingResponse:
    try:
        selected = await documents.download(user.tenant_id, document_id, user.id, version)
    except (DocumentNotFoundError, DocumentUnavailableError, StorageError) as exc:
        raise service_error(exc) from exc
    storage: S3Storage = request.app.state.storage
    return StreamingResponse(
        storage.iter_bytes(selected.storage_key),
        media_type=selected.content_type,
        headers={
            "Content-Disposition": content_disposition(selected.safe_filename),
            "ETag": f'"sha256:{selected.checksum_sha256}"',
            "X-Content-SHA256": selected.checksum_sha256,
        },
    )


@router.patch("/{document_id}", response_model=DocumentResponse)
async def update_document(
    document_id: uuid.UUID,
    payload: DocumentMetadataUpdate,
    response: Response,
    user: Manager,
    documents: Service,
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> DocumentResponse:
    try:
        result = await documents.update_metadata(
            user.tenant_id,
            document_id,
            user.id,
            parse_if_match(if_match),
            category=payload.category,
            classification=payload.classification,
            retention_until=payload.retention_until,
            update_retention="retention_until" in payload.model_fields_set,
        )
    except (DocumentConflictError, DocumentNotFoundError, DocumentUnavailableError) as exc:
        raise service_error(exc) from exc
    response.headers["ETag"] = etag(result.lock_version)
    return result


@router.post("/{document_id}/links", response_model=DocumentResponse)
async def add_document_link(
    document_id: uuid.UUID,
    payload: DocumentLinkCreate,
    request: Request,
    user: Manager,
    documents: Service,
    settings: SettingsDependency,
    authorization: Authorization,
) -> DocumentResponse:
    await validate_resource(
        request,
        settings,
        authorization,
        user.tenant_id,
        payload.resource_type,
        payload.resource_id,
    )
    try:
        return await documents.add_link(
            user.tenant_id,
            document_id,
            user.id,
            payload.resource_type,
            payload.resource_id,
        )
    except (DocumentConflictError, DocumentNotFoundError, DocumentUnavailableError) as exc:
        raise service_error(exc) from exc


@router.delete("/{document_id}/links/{link_id}", response_model=DocumentResponse)
async def remove_document_link(
    document_id: uuid.UUID,
    link_id: uuid.UUID,
    user: Manager,
    documents: Service,
) -> DocumentResponse:
    try:
        return await documents.remove_link(user.tenant_id, document_id, link_id, user.id)
    except (DocumentConflictError, DocumentNotFoundError, DocumentUnavailableError) as exc:
        raise service_error(exc) from exc


@router.post("/{document_id}/archive", response_model=DocumentResponse)
async def archive_document(
    document_id: uuid.UUID, user: Manager, documents: Service
) -> DocumentResponse:
    try:
        return await documents.set_lifecycle(user.tenant_id, document_id, user.id, "archive")
    except (DocumentConflictError, DocumentNotFoundError, DocumentUnavailableError) as exc:
        raise service_error(exc) from exc


@router.delete("/{document_id}", response_model=DocumentResponse)
async def delete_document(
    document_id: uuid.UUID, user: Deleter, documents: Service
) -> DocumentResponse:
    try:
        return await documents.set_lifecycle(user.tenant_id, document_id, user.id, "delete")
    except (DocumentConflictError, DocumentNotFoundError, DocumentUnavailableError) as exc:
        raise service_error(exc) from exc


@router.post("/{document_id}/restore", response_model=DocumentResponse)
async def restore_document(
    document_id: uuid.UUID, user: Deleter, documents: Service
) -> DocumentResponse:
    try:
        return await documents.set_lifecycle(user.tenant_id, document_id, user.id, "restore")
    except (DocumentConflictError, DocumentNotFoundError, DocumentUnavailableError) as exc:
        raise service_error(exc) from exc


@router.get("/{document_id}/audit", response_model=list[AuditEventResponse])
async def document_audit(
    document_id: uuid.UUID, user: Auditor, documents: Service
) -> list[AuditEventResponse]:
    try:
        events = await documents.audit_events(user.tenant_id, document_id)
    except DocumentNotFoundError as exc:
        raise service_error(exc) from exc
    return [AuditEventResponse.model_validate(item) for item in events]
