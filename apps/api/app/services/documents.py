import hashlib
import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.repositories.document import DocumentRepository
from app.repositories.legal import LegalRepository
from app.schemas.document import DocumentEntityType
from app.services.audit import AuditService
from app.services.storage import LocalStorage


class DocumentResourceNotFoundError(Exception):
    pass


class DocumentStorageError(Exception):
    pass


class DocumentService:
    def __init__(self, session: AsyncSession, storage: LocalStorage) -> None:
        self.session = session
        self.storage = storage
        self.repo = DocumentRepository(session)
        self.legal = LegalRepository(session)
        self.audit = AuditService(session)

    async def upload(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        entity_type: DocumentEntityType,
        entity_id: uuid.UUID,
        category: str,
        filename: str,
        content_type: str,
        content: bytes,
    ) -> Document:
        await self._ensure_entity_exists(tenant_id, entity_type, entity_id)
        document = Document(
            tenant_id=tenant_id,
            entity_type=entity_type,
            entity_id=entity_id,
            category=category,
            original_filename=filename,
            content_type=content_type,
            size_bytes=len(content),
            checksum_sha256=hashlib.sha256(content).hexdigest(),
            storage_key="pending",
            uploaded_by_user_id=actor_id,
        )
        self.session.add(document)
        await self.session.flush()
        storage_key = self.storage.write(str(tenant_id), str(document.id), content)
        document.storage_key = storage_key
        self.audit.record_created(
            tenant_id=tenant_id,
            actor_user_id=actor_id,
            entity_type="Document",
            entity_id=document.id,
            new_value={"entity_type": entity_type, "category": category, "filename": filename},
        )
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            self.storage.delete(storage_key)
            raise DocumentStorageError from exc
        await self.session.refresh(document)
        return document

    async def list_for_entity(
        self, tenant_id: uuid.UUID, entity_type: DocumentEntityType, entity_id: uuid.UUID
    ) -> list[Document]:
        await self._ensure_entity_exists(tenant_id, entity_type, entity_id)
        return await self.repo.list_for_entity(tenant_id, entity_type, entity_id)

    async def download_path(
        self, tenant_id: uuid.UUID, document_id: uuid.UUID
    ) -> tuple[Document, str]:
        document = await self.repo.get_by_id_for_tenant(document_id, tenant_id)
        if document is None:
            raise DocumentResourceNotFoundError
        try:
            return document, str(self.storage.read(document.storage_key))
        except FileNotFoundError as exc:
            raise DocumentStorageError from exc

    async def _ensure_entity_exists(
        self, tenant_id: uuid.UUID, entity_type: DocumentEntityType, entity_id: uuid.UUID
    ) -> None:
        if entity_type == DocumentEntityType.LEGAL_CASE:
            exists = await self.legal.case(entity_id, tenant_id) is not None
        elif entity_type == DocumentEntityType.COURT_DECISION:
            exists = await self.legal.decision(entity_id, tenant_id) is not None
        elif entity_type == DocumentEntityType.LEGAL_OBLIGATION:
            exists = await self.legal.obligation(entity_id, tenant_id) is not None
        else:
            exists = await self.legal.enforcement(entity_id, tenant_id) is not None
        if not exists:
            raise DocumentResourceNotFoundError
