import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from app.core.security import (
    AuthenticatedUser,
    SessionDependency,
    SettingsDependency,
    require_permission,
)
from app.schemas.document import DocumentEntityType, DocumentResponse
from app.services.documents import (
    DocumentResourceNotFoundError,
    DocumentService,
    DocumentStorageError,
)
from app.services.storage import LocalStorage

router = APIRouter(prefix="/documents")
LegalManager = Annotated[AuthenticatedUser, Depends(require_permission("legal.manage"))]


def document_service(session: SessionDependency, settings: SettingsDependency) -> DocumentService:
    return DocumentService(session, LocalStorage(settings.document_storage_path))


DocumentServiceDependency = Annotated[DocumentService, Depends(document_service)]


def document_error(exc: Exception) -> HTTPException:
    if isinstance(exc, DocumentResourceNotFoundError):
        return HTTPException(
            status.HTTP_404_NOT_FOUND, "The requested document resource was not found."
        )
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Document storage is unavailable.")


@router.get("", response_model=list[DocumentResponse])
async def documents(
    user: LegalManager,
    service: DocumentServiceDependency,
    entity_type: DocumentEntityType | None = None,
    entity_id: uuid.UUID | None = None,
) -> list[DocumentResponse]:
    if entity_type is None and entity_id is None:
        return [
            DocumentResponse.model_validate(item)
            for item in await service.list_for_tenant(user.tenant_id)
        ]
    if entity_type is None or entity_id is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "entity_type and entity_id must be provided together.",
        )
    try:
        return [
            DocumentResponse.model_validate(item)
            for item in await service.list_for_entity(user.tenant_id, entity_type, entity_id)
        ]
    except DocumentResourceNotFoundError as exc:
        raise document_error(exc) from exc


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    entity_type: Annotated[DocumentEntityType, Form()],
    entity_id: Annotated[uuid.UUID, Form()],
    category: Annotated[str, Form(min_length=1, max_length=100)],
    file: Annotated[UploadFile, File()],
    user: LegalManager,
    settings: SettingsDependency,
    service: DocumentServiceDependency,
) -> DocumentResponse:
    content = await file.read(settings.max_document_size_bytes + 1)
    if len(content) > settings.max_document_size_bytes:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Document exceeds the size limit."
        )
    filename = file.filename or "unnamed"
    try:
        document = await service.upload(
            tenant_id=user.tenant_id,
            actor_id=user.id,
            entity_type=entity_type,
            entity_id=entity_id,
            category=category.strip(),
            filename=filename,
            content_type=file.content_type or "application/octet-stream",
            content=content,
        )
    except (DocumentResourceNotFoundError, DocumentStorageError) as exc:
        raise document_error(exc) from exc
    return DocumentResponse.model_validate(document)


@router.get("/{document_id}/download")
async def download_document(
    document_id: uuid.UUID,
    user: LegalManager,
    service: DocumentServiceDependency,
) -> FileResponse:
    try:
        document, path = await service.download_path(user.tenant_id, document_id)
    except (DocumentResourceNotFoundError, DocumentStorageError) as exc:
        raise document_error(exc) from exc
    return FileResponse(path, media_type=document.content_type, filename=document.original_filename)
