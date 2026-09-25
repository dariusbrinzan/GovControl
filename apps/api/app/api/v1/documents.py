import uuid
from io import BytesIO
from typing import Annotated
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse

from app.core.observability import current_request_id
from app.core.security import (
    AuthenticatedUser,
    SessionDependency,
    SettingsDependency,
    require_any_permission,
)
from app.schemas.document import DocumentEntityType, DocumentResponse
from app.services.documents import (
    DocumentResourceNotFoundError,
    DocumentService,
    DocumentStorageError,
)
from app.services.storage import storage_from_settings

router = APIRouter(prefix="/documents")
DocumentManager = Annotated[
    AuthenticatedUser, Depends(require_any_permission("legal.manage", "contracts.manage"))
]
AuthorizationHeader = Annotated[str | None, Header(alias="Authorization")]


async def ensure_contract_exists(
    entity_type: DocumentEntityType,
    entity_id: uuid.UUID,
    tenant_id: uuid.UUID,
    authorization: str | None,
    settings: SettingsDependency,
) -> None:
    if entity_type != DocumentEntityType.CONTRACT:
        return
    if authorization is None and settings.internal_service_token is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication is required.")
    if settings.internal_service_token is not None:
        path = f"/internal/contracts/{entity_id}"
        headers = {
            "X-Service-Token": settings.internal_service_token.get_secret_value(),
            "X-Tenant-ID": str(tenant_id),
        }
    else:
        path = f"/contracts/{entity_id}"
        headers = {"Authorization": authorization or ""}
    request_id = current_request_id()
    if request_id is not None:
        headers["X-Request-ID"] = str(request_id)
    try:
        async with httpx.AsyncClient(timeout=settings.service_request_timeout_seconds) as client:
            response = await client.get(
                f"{settings.contracts_api_url.rstrip('/')}{path}",
                headers=headers,
            )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "GovContracts is unavailable."
        ) from exc
    if response.status_code == status.HTTP_404_NOT_FOUND:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Contract not found in this tenant.")
    if response.status_code != status.HTTP_200_OK:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Contract could not be verified.")


def document_service(session: SessionDependency, settings: SettingsDependency) -> DocumentService:
    return DocumentService(session, storage_from_settings(settings))


DocumentServiceDependency = Annotated[DocumentService, Depends(document_service)]


def document_error(exc: Exception) -> HTTPException:
    if isinstance(exc, DocumentResourceNotFoundError):
        return HTTPException(
            status.HTTP_404_NOT_FOUND, "The requested document resource was not found."
        )
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Document storage is unavailable.")


@router.get("", response_model=list[DocumentResponse])
async def documents(
    user: DocumentManager,
    service: DocumentServiceDependency,
    settings: SettingsDependency,
    authorization: AuthorizationHeader = None,
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
    await ensure_contract_exists(entity_type, entity_id, user.tenant_id, authorization, settings)
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
    user: DocumentManager,
    settings: SettingsDependency,
    service: DocumentServiceDependency,
    authorization: AuthorizationHeader = None,
) -> DocumentResponse:
    await ensure_contract_exists(entity_type, entity_id, user.tenant_id, authorization, settings)
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
    user: DocumentManager,
    service: DocumentServiceDependency,
) -> StreamingResponse:
    try:
        document, content = await service.download(user.tenant_id, document_id)
    except (DocumentResourceNotFoundError, DocumentStorageError) as exc:
        raise document_error(exc) from exc
    encoded_filename = quote(document.original_filename)
    return StreamingResponse(
        BytesIO(content),
        media_type=document.content_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"},
    )
