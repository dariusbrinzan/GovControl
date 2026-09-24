import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document


class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_for_entity(
        self, tenant_id: uuid.UUID, entity_type: str, entity_id: uuid.UUID
    ) -> list[Document]:
        return list(
            await self.session.scalars(
                select(Document)
                .where(
                    Document.tenant_id == tenant_id,
                    Document.entity_type == entity_type,
                    Document.entity_id == entity_id,
                )
                .order_by(Document.created_at.desc())
            )
        )

    async def list_for_tenant(self, tenant_id: uuid.UUID, limit: int = 500) -> list[Document]:
        return list(
            await self.session.scalars(
                select(Document)
                .where(Document.tenant_id == tenant_id)
                .order_by(Document.created_at.desc(), Document.id)
                .limit(limit)
            )
        )

    async def get_by_id_for_tenant(
        self, document_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> Document | None:
        item: Document | None = await self.session.scalar(
            select(Document).where(Document.id == document_id, Document.tenant_id == tenant_id)
        )
        return item
