import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from documents_app.config import Settings
from documents_app.models import Document, DocumentState, DocumentVersion
from documents_app.service import (
    DocumentConflictError,
    DocumentService,
    DocumentUnavailableError,
)
from documents_app.worker import event_envelope


def test_optimistic_concurrency_rejects_stale_etag() -> None:
    document = SimpleNamespace(lock_version=4)
    with pytest.raises(DocumentConflictError):
        DocumentService._check_version(document, 3)  # type: ignore[arg-type]


def test_outbox_envelope_contains_idempotency_and_tenant_without_content() -> None:
    event_id, tenant_id, aggregate_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    event = SimpleNamespace(
        id=event_id,
        tenant_id=tenant_id,
        event_type="document.available.v1",
        aggregate_type="Document",
        aggregate_id=aggregate_id,
        created_at=SimpleNamespace(isoformat=lambda: "2026-09-26T10:00:00+00:00"),
        payload={"version_id": str(uuid.uuid4())},
    )
    envelope = event_envelope(event)  # type: ignore[arg-type]
    assert envelope["id"] == str(event_id)
    assert envelope["tenant_id"] == str(tenant_id)
    assert "content" not in envelope["payload"]


def service_with_session(session: Any) -> DocumentService:
    return DocumentService(
        session,
        SimpleNamespace(),  # type: ignore[arg-type]
        Settings(database_url="postgresql+asyncpg://user:password@localhost/test"),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("state", [DocumentState.QUARANTINED, DocumentState.REJECTED])
async def test_download_rejects_versions_that_are_not_available(
    state: DocumentState,
) -> None:
    tenant_id, document_id = uuid.uuid4(), uuid.uuid4()
    document = Document(
        id=document_id,
        tenant_id=tenant_id,
        category="TEST",
        classification="INTERNAL",
        state=state,
        current_version_number=1,
        lock_version=1,
        created_by_user_id=uuid.uuid4(),
    )
    version = DocumentVersion(
        id=uuid.uuid4(),
        document_id=document_id,
        tenant_id=tenant_id,
        version_number=1,
        original_filename="test.txt",
        safe_filename="test.txt",
        content_type="text/plain",
        size_bytes=4,
        checksum_sha256="0" * 64,
        storage_key=f"{tenant_id}/{document_id}/{uuid.uuid4()}",
        state=state,
        created_by_user_id=uuid.uuid4(),
    )
    session = MagicMock()
    session.scalar = AsyncMock()
    session.commit = AsyncMock()
    session.scalar.side_effect = [document, version]

    with pytest.raises(DocumentUnavailableError):
        await service_with_session(session).download(
            tenant_id, document_id, uuid.uuid4(), None
        )

    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_soft_delete_and_restore_preserve_document() -> None:
    tenant_id, document_id, actor_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    document = Document(
        id=document_id,
        tenant_id=tenant_id,
        category="TEST",
        classification="INTERNAL",
        state=DocumentState.AVAILABLE,
        current_version_number=1,
        lock_version=1,
        created_by_user_id=actor_id,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    session = MagicMock()
    session.scalar = AsyncMock()
    session.commit = AsyncMock()
    session.scalar.return_value = document
    documents = service_with_session(session)
    documents.get = AsyncMock(return_value=SimpleNamespace())  # type: ignore[method-assign]

    await documents.set_lifecycle(tenant_id, document_id, actor_id, "delete")
    assert document.deleted_at is not None
    assert document.lock_version == 2

    await documents.set_lifecycle(tenant_id, document_id, actor_id, "restore")
    assert document.deleted_at is None
    assert document.lock_version == 3
    assert session.commit.await_count == 2
