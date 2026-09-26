import hashlib
import re
import unicodedata
import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import PurePath
from tempfile import SpooledTemporaryFile
from typing import IO

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from documents_app.config import Settings
from documents_app.models import (
    Document,
    DocumentAuditEvent,
    DocumentLink,
    DocumentState,
    DocumentVersion,
    IdempotencyRecord,
    OutboxEvent,
    ResourceType,
)
from documents_app.observability import current_request_id
from documents_app.schemas import (
    DocumentLinkResponse,
    DocumentResponse,
    DocumentVersionResponse,
)
from documents_app.storage import S3Storage

SAFE_FILENAME = re.compile(r"[^\w.()\- ]+", re.UNICODE)


class DocumentNotFoundError(Exception):
    pass


class DocumentConflictError(Exception):
    pass


class DocumentUnavailableError(Exception):
    pass


def normalize_filename(filename: str, allowed_extensions: frozenset[str]) -> str:
    normalized = unicodedata.normalize("NFKC", filename).strip()
    if not normalized or normalized in {".", ".."}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "A valid filename is required.")
    if PurePath(normalized).name != normalized or "/" in normalized or "\\" in normalized:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unsafe filename.")
    safe = SAFE_FILENAME.sub("_", normalized).strip(" .")
    if not safe or len(safe) > 255:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "A valid filename is required.")
    extension = PurePath(safe).suffix.lower()
    if extension not in allowed_extensions:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "File extension is not allowed."
        )
    return safe


async def spool_upload(
    upload: UploadFile, settings: Settings
) -> tuple[IO[bytes], int, str, str, str, str]:
    original = upload.filename or ""
    safe = normalize_filename(original, settings.extension_allowlist)
    content_type = (upload.content_type or "application/octet-stream").split(";", 1)[0].lower()
    if content_type not in settings.content_type_allowlist:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Content type is not allowed.")
    target = SpooledTemporaryFile(max_size=min(settings.max_upload_size_bytes, 2 * 1024 * 1024))
    digest = hashlib.sha256()
    size = 0
    try:
        while chunk := await upload.read(settings.upload_chunk_size_bytes):
            size += len(chunk)
            if size > settings.max_upload_size_bytes:
                raise HTTPException(
                    status.HTTP_413_CONTENT_TOO_LARGE, "Document exceeds the size limit."
                )
            digest.update(chunk)
            target.write(chunk)
        if size == 0:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "Empty files are not allowed."
            )
        target.seek(0)
        return target, size, digest.hexdigest(), original, safe, content_type
    except Exception:
        target.close()
        raise
    finally:
        await upload.close()


class DocumentService:
    def __init__(self, session: AsyncSession, storage: S3Storage, settings: Settings) -> None:
        self.session = session
        self.storage = storage
        self.settings = settings

    async def create(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        resource_type: ResourceType,
        resource_id: uuid.UUID,
        category: str,
        classification: str,
        retention_until: date | None,
        upload: UploadFile,
        idempotency_key: str | None,
    ) -> DocumentResponse:
        spool, size, checksum, original, safe, content_type = await spool_upload(
            upload, self.settings
        )
        document_id = uuid.uuid4()
        version_id = uuid.uuid4()
        request_hash = hashlib.sha256(
            f"{resource_type}:{resource_id}:{category}:{classification}:{retention_until}:{checksum}".encode()
        ).hexdigest()
        if idempotency_key:
            existing = await self.session.scalar(
                select(IdempotencyRecord).where(
                    IdempotencyRecord.tenant_id == tenant_id,
                    IdempotencyRecord.key == idempotency_key,
                )
            )
            if existing is not None:
                spool.close()
                if existing.request_hash != request_hash:
                    raise DocumentConflictError("Idempotency key was used for another request.")
                return await self.get(tenant_id, existing.document_id, include_deleted=True)
        state = (
            DocumentState.AVAILABLE
            if self.settings.malware_scanner_mode == "local_clean"
            else DocumentState.QUARANTINED
        )
        storage_key = ""
        try:
            storage_key = await run_in_threadpool(
                self.storage.upload,
                tenant_id,
                document_id,
                version_id,
                spool,
                content_type,
            )
        finally:
            spool.close()
        now = datetime.now(UTC)
        document = Document(
            id=document_id,
            tenant_id=tenant_id,
            category=category.strip(),
            classification=classification.strip().upper(),
            retention_until=retention_until,
            state=state,
            current_version_number=1,
            lock_version=1,
            created_by_user_id=actor_id,
        )
        version = DocumentVersion(
            id=version_id,
            document_id=document_id,
            tenant_id=tenant_id,
            version_number=1,
            original_filename=original,
            safe_filename=safe,
            content_type=content_type,
            size_bytes=size,
            checksum_sha256=checksum,
            storage_key=storage_key,
            state=state,
            created_by_user_id=actor_id,
            scanned_at=now if state == DocumentState.AVAILABLE else None,
        )
        link = DocumentLink(
            document_id=document_id,
            tenant_id=tenant_id,
            resource_type=resource_type,
            resource_id=resource_id,
            created_by_user_id=actor_id,
        )
        self.session.add_all([document, version, link])
        self._audit(document, actor_id, "document.uploaded", {"checksum": checksum})
        self._event(document, "document.uploaded.v1", {"version_id": str(version_id)})
        if state == DocumentState.AVAILABLE:
            self._audit(document, actor_id, "document.scan_clean", None)
            self._event(document, "document.available.v1", {"version_id": str(version_id)})
        if idempotency_key:
            self.session.add(
                IdempotencyRecord(
                    tenant_id=tenant_id,
                    key=idempotency_key,
                    request_hash=request_hash,
                    document_id=document_id,
                )
            )
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            await run_in_threadpool(self.storage.delete, storage_key)
            raise DocumentConflictError("Document upload conflicts with existing data.") from exc
        return await self.get(tenant_id, document_id)

    async def add_version(
        self,
        *,
        tenant_id: uuid.UUID,
        document_id: uuid.UUID,
        actor_id: uuid.UUID,
        expected_version: int,
        upload: UploadFile,
    ) -> DocumentResponse:
        document = await self._document(tenant_id, document_id, for_update=True)
        if document.deleted_at is not None:
            raise DocumentNotFoundError
        if document.lock_version != expected_version:
            raise DocumentConflictError("Document was modified by another request.")
        spool, size, checksum, original, safe, content_type = await spool_upload(
            upload, self.settings
        )
        duplicate = await self.session.scalar(
            select(DocumentVersion.id).where(
                DocumentVersion.document_id == document_id,
                DocumentVersion.checksum_sha256 == checksum,
            )
        )
        if duplicate is not None:
            spool.close()
            raise DocumentConflictError("This content already exists as a document version.")
        version_id = uuid.uuid4()
        version_number = document.current_version_number + 1
        state = (
            DocumentState.AVAILABLE
            if self.settings.malware_scanner_mode == "local_clean"
            else DocumentState.QUARANTINED
        )
        try:
            storage_key = await run_in_threadpool(
                self.storage.upload,
                tenant_id,
                document_id,
                version_id,
                spool,
                content_type,
            )
        finally:
            spool.close()
        version = DocumentVersion(
            id=version_id,
            document_id=document_id,
            tenant_id=tenant_id,
            version_number=version_number,
            original_filename=original,
            safe_filename=safe,
            content_type=content_type,
            size_bytes=size,
            checksum_sha256=checksum,
            storage_key=storage_key,
            state=state,
            created_by_user_id=actor_id,
            scanned_at=datetime.now(UTC) if state == DocumentState.AVAILABLE else None,
        )
        document.current_version_number = version_number
        document.lock_version += 1
        document.state = state
        self.session.add(version)
        self._audit(document, actor_id, "document.version_created", {"version": version_number})
        self._event(document, "document.version_created.v1", {"version_id": str(version_id)})
        if state == DocumentState.AVAILABLE:
            self._event(document, "document.available.v1", {"version_id": str(version_id)})
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            await run_in_threadpool(self.storage.delete, storage_key)
            raise DocumentConflictError("Document version conflicts with existing data.") from exc
        return await self.get(tenant_id, document_id)

    async def list(
        self,
        tenant_id: uuid.UUID,
        *,
        page: int,
        page_size: int,
        query: str | None,
        state: DocumentState | None,
        resource_type: ResourceType | None,
        resource_id: uuid.UUID | None,
        include_deleted: bool,
    ) -> tuple[list[DocumentResponse], int]:
        statement = select(Document).where(Document.tenant_id == tenant_id)
        count_statement = select(func.count()).select_from(Document).where(
            Document.tenant_id == tenant_id
        )
        if not include_deleted:
            statement = statement.where(Document.deleted_at.is_(None))
            count_statement = count_statement.where(Document.deleted_at.is_(None))
        if state is not None:
            statement = statement.where(Document.state == state)
            count_statement = count_statement.where(Document.state == state)
        if query:
            pattern = f"%{query.strip()}%"
            version_ids = select(DocumentVersion.document_id).where(
                DocumentVersion.tenant_id == tenant_id,
                or_(
                    DocumentVersion.original_filename.ilike(pattern),
                    DocumentVersion.checksum_sha256.ilike(pattern),
                ),
            )
            statement = statement.where(
                or_(Document.category.ilike(pattern), Document.id.in_(version_ids))
            )
            count_statement = count_statement.where(
                or_(Document.category.ilike(pattern), Document.id.in_(version_ids))
            )
        if resource_type is not None or resource_id is not None:
            if resource_type is None or resource_id is None:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT,
                    "resource_type and resource_id must be provided together.",
                )
            linked = select(DocumentLink.document_id).where(
                DocumentLink.tenant_id == tenant_id,
                DocumentLink.resource_type == resource_type,
                DocumentLink.resource_id == resource_id,
            )
            statement = statement.where(Document.id.in_(linked))
            count_statement = count_statement.where(Document.id.in_(linked))
        total = int(await self.session.scalar(count_statement) or 0)
        documents = list(
            await self.session.scalars(
                statement.order_by(Document.created_at.desc(), Document.id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        return [await self._response(item) for item in documents], total

    async def get(
        self, tenant_id: uuid.UUID, document_id: uuid.UUID, *, include_deleted: bool = False
    ) -> DocumentResponse:
        document = await self._document(tenant_id, document_id)
        if document.deleted_at is not None and not include_deleted:
            raise DocumentNotFoundError
        return await self._response(document)

    async def download(
        self,
        tenant_id: uuid.UUID,
        document_id: uuid.UUID,
        actor_id: uuid.UUID,
        version_number: int | None,
    ) -> DocumentVersion:
        document = await self._document(tenant_id, document_id)
        if document.deleted_at is not None:
            raise DocumentNotFoundError
        selected = version_number or document.current_version_number
        version = await self.session.scalar(
            select(DocumentVersion).where(
                DocumentVersion.document_id == document_id,
                DocumentVersion.tenant_id == tenant_id,
                DocumentVersion.version_number == selected,
            )
        )
        if version is None:
            raise DocumentNotFoundError
        if version.state != DocumentState.AVAILABLE:
            raise DocumentUnavailableError
        self._audit(document, actor_id, "document.downloaded", {"version": selected})
        await self.session.commit()
        return version

    async def update_metadata(
        self,
        tenant_id: uuid.UUID,
        document_id: uuid.UUID,
        actor_id: uuid.UUID,
        expected_version: int,
        *,
        category: str | None,
        classification: str | None,
        retention_until: date | None,
        update_retention: bool,
    ) -> DocumentResponse:
        document = await self._document(tenant_id, document_id, for_update=True)
        self._check_version(document, expected_version)
        if category is not None:
            document.category = category.strip()
        if classification is not None:
            document.classification = classification.strip().upper()
        if update_retention:
            document.retention_until = retention_until
        document.lock_version += 1
        self._audit(document, actor_id, "document.metadata_updated", None)
        await self.session.commit()
        return await self.get(tenant_id, document_id, include_deleted=True)

    async def add_link(
        self,
        tenant_id: uuid.UUID,
        document_id: uuid.UUID,
        actor_id: uuid.UUID,
        resource_type: ResourceType,
        resource_id: uuid.UUID,
    ) -> DocumentResponse:
        document = await self._document(tenant_id, document_id)
        if document.deleted_at is not None:
            raise DocumentNotFoundError
        self.session.add(
            DocumentLink(
                document_id=document_id,
                tenant_id=tenant_id,
                resource_type=resource_type,
                resource_id=resource_id,
                created_by_user_id=actor_id,
            )
        )
        document.lock_version += 1
        self._audit(
            document,
            actor_id,
            "document.linked",
            {"resource_type": resource_type, "resource_id": str(resource_id)},
        )
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise DocumentConflictError("Document is already linked to this resource.") from exc
        return await self.get(tenant_id, document_id)

    async def remove_link(
        self, tenant_id: uuid.UUID, document_id: uuid.UUID, link_id: uuid.UUID, actor_id: uuid.UUID
    ) -> DocumentResponse:
        document = await self._document(tenant_id, document_id, for_update=True)
        link = await self.session.scalar(
            select(DocumentLink).where(
                DocumentLink.id == link_id,
                DocumentLink.document_id == document_id,
                DocumentLink.tenant_id == tenant_id,
            )
        )
        if link is None:
            raise DocumentNotFoundError
        await self.session.delete(link)
        document.lock_version += 1
        self._audit(document, actor_id, "document.unlinked", {"link_id": str(link_id)})
        await self.session.commit()
        return await self.get(tenant_id, document_id)

    async def set_lifecycle(
        self,
        tenant_id: uuid.UUID,
        document_id: uuid.UUID,
        actor_id: uuid.UUID,
        action: str,
    ) -> DocumentResponse:
        document = await self._document(tenant_id, document_id, for_update=True)
        now = datetime.now(UTC)
        if action == "archive":
            document.archived_at = now
            event = "document.archived.v1"
        elif action == "delete":
            if document.retention_until is not None and document.retention_until > now.date():
                raise DocumentConflictError("Document is protected by its retention policy.")
            document.deleted_at = now
            event = "document.deleted.v1"
        elif action == "restore":
            document.deleted_at = None
            event = "document.restored.v1"
        else:
            raise ValueError(action)
        document.lock_version += 1
        self._audit(document, actor_id, f"document.{action}d", None)
        self._event(document, event, None)
        await self.session.commit()
        return await self.get(tenant_id, document_id, include_deleted=True)

    async def audit_events(
        self, tenant_id: uuid.UUID, document_id: uuid.UUID
    ) -> Sequence[DocumentAuditEvent]:
        await self._document(tenant_id, document_id)
        return list(
            await self.session.scalars(
                select(DocumentAuditEvent)
                .where(
                    DocumentAuditEvent.tenant_id == tenant_id,
                    DocumentAuditEvent.document_id == document_id,
                )
                .order_by(DocumentAuditEvent.created_at.desc(), DocumentAuditEvent.id)
            )
        )

    async def _document(
        self, tenant_id: uuid.UUID, document_id: uuid.UUID, *, for_update: bool = False
    ) -> Document:
        statement = select(Document).where(
            Document.id == document_id, Document.tenant_id == tenant_id
        )
        if for_update:
            statement = statement.with_for_update()
        document = await self.session.scalar(statement)
        if document is None:
            raise DocumentNotFoundError
        return document

    @staticmethod
    def _check_version(document: Document, expected_version: int) -> None:
        if document.lock_version != expected_version:
            raise DocumentConflictError("Document was modified by another request.")

    async def _response(self, document: Document) -> DocumentResponse:
        version = await self.session.scalar(
            select(DocumentVersion).where(
                DocumentVersion.document_id == document.id,
                DocumentVersion.version_number == document.current_version_number,
            )
        )
        if version is None:
            raise DocumentUnavailableError
        links = list(
            await self.session.scalars(
                select(DocumentLink)
                .where(
                    DocumentLink.document_id == document.id,
                    DocumentLink.tenant_id == document.tenant_id,
                )
                .order_by(DocumentLink.created_at, DocumentLink.id)
            )
        )
        return DocumentResponse(
            id=document.id,
            tenant_id=document.tenant_id,
            category=document.category,
            classification=document.classification,
            retention_until=document.retention_until,
            state=document.state,
            current_version_number=document.current_version_number,
            lock_version=document.lock_version,
            created_by_user_id=document.created_by_user_id,
            archived_at=document.archived_at,
            deleted_at=document.deleted_at,
            created_at=document.created_at,
            updated_at=document.updated_at,
            current_version=DocumentVersionResponse.model_validate(version),
            links=[DocumentLinkResponse.model_validate(link) for link in links],
        )

    def _audit(
        self,
        document: Document,
        actor_id: uuid.UUID,
        action: str,
        payload: dict[str, object] | None,
    ) -> None:
        self.session.add(
            DocumentAuditEvent(
                tenant_id=document.tenant_id,
                document_id=document.id,
                actor_user_id=actor_id,
                action=action,
                request_id=current_request_id(),
                payload=payload,
            )
        )

    def _event(
        self, document: Document, event_type: str, payload: dict[str, object] | None
    ) -> None:
        self.session.add(
            OutboxEvent(
                tenant_id=document.tenant_id,
                event_type=event_type,
                aggregate_type="Document",
                aggregate_id=document.id,
                payload=payload or {},
            )
        )
