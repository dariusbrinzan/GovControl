import argparse
import asyncio
import hashlib
import json
import uuid
from datetime import datetime
from pathlib import Path
from tempfile import SpooledTemporaryFile
from typing import Any

from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from documents_app.config import get_settings
from documents_app.database import session_factory
from documents_app.models import (
    Document,
    DocumentAuditEvent,
    DocumentLink,
    DocumentState,
    DocumentVersion,
    OutboxEvent,
    ResourceType,
)
from documents_app.service import normalize_filename
from documents_app.storage import S3Storage


def load_manifest(source: Path) -> list[dict[str, Any]]:
    payload = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    if payload.get("format") != "govcontrol-legacy-documents-v1":
        raise RuntimeError("Unsupported legacy document manifest.")
    items = payload.get("items")
    if not isinstance(items, list) or payload.get("count") != len(items):
        raise RuntimeError("Legacy document manifest count is invalid.")
    return items


def checksum_stream(source: Any, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    while chunk := source.read(chunk_size):
        digest.update(chunk)
    return digest.hexdigest()


async def backfill(source: Path) -> dict[str, int]:
    source = source.resolve()
    settings = get_settings()
    storage = S3Storage(settings)
    items = load_manifest(source)
    imported = 0
    skipped = 0
    verified = 0
    for item in items:
        document_id = uuid.UUID(item["id"])
        tenant_id = uuid.UUID(item["tenant_id"])
        actor_id = uuid.UUID(item["uploaded_by_user_id"])
        version_id = uuid.uuid5(uuid.NAMESPACE_URL, f"govcontrol:document-version:{document_id}:1")
        blob = (source / item["blob"]).resolve()
        if not blob.is_relative_to(source) or not blob.is_file():
            raise RuntimeError(f"Invalid or missing blob for {document_id}")
        expected_checksum = str(item["checksum_sha256"])
        with blob.open("rb") as source_blob:
            actual_checksum = checksum_stream(source_blob)
        if actual_checksum != expected_checksum or blob.stat().st_size != int(item["size_bytes"]):
            raise RuntimeError(f"Exported bytes do not match manifest for {document_id}")
        async with session_factory() as session:
            existing = await session.get(Document, document_id)
            if existing is not None:
                version = await session.scalar(
                    select(DocumentVersion).where(
                        DocumentVersion.document_id == document_id,
                        DocumentVersion.version_number == 1,
                    )
                )
                if version is None or version.checksum_sha256 != expected_checksum:
                    raise RuntimeError(f"Existing backfill conflicts for {document_id}")
                skipped += 1
                verified += 1
                continue
            safe_filename = normalize_filename(
                str(item["original_filename"]), settings.extension_allowlist
            )
            with blob.open("rb") as content:
                storage_key = await run_in_threadpool(
                    storage.upload,
                    tenant_id,
                    document_id,
                    version_id,
                    content,
                    str(item["content_type"]),
                )
            try:
                with SpooledTemporaryFile(max_size=2 * 1024 * 1024) as copied:
                    await run_in_threadpool(storage.download_to, storage_key, copied)
                    copied_checksum = checksum_stream(copied)
                if copied_checksum != expected_checksum:
                    raise RuntimeError(f"Target checksum mismatch for {document_id}")
                created_at = datetime.fromisoformat(item["created_at"])
                document = Document(
                    id=document_id,
                    tenant_id=tenant_id,
                    category=str(item["category"]),
                    classification=str(item["classification"]),
                    state=DocumentState.AVAILABLE,
                    current_version_number=1,
                    lock_version=1,
                    created_by_user_id=actor_id,
                    created_at=created_at,
                    updated_at=created_at,
                )
                session.add_all(
                    [
                        document,
                        DocumentVersion(
                            id=version_id,
                            document_id=document_id,
                            tenant_id=tenant_id,
                            version_number=1,
                            original_filename=str(item["original_filename"]),
                            safe_filename=safe_filename,
                            content_type=str(item["content_type"]),
                            size_bytes=int(item["size_bytes"]),
                            checksum_sha256=expected_checksum,
                            storage_key=storage_key,
                            state=DocumentState.AVAILABLE,
                            created_by_user_id=actor_id,
                            created_at=created_at,
                            scanned_at=created_at,
                        ),
                        DocumentLink(
                            document_id=document_id,
                            tenant_id=tenant_id,
                            resource_type=ResourceType(str(item["resource_type"])),
                            resource_id=uuid.UUID(item["resource_id"]),
                            created_by_user_id=actor_id,
                            created_at=created_at,
                        ),
                        DocumentAuditEvent(
                            tenant_id=tenant_id,
                            document_id=document_id,
                            actor_user_id=actor_id,
                            action="document.backfilled",
                            payload={"legacy_document_id": str(document_id)},
                            created_at=created_at,
                        ),
                        OutboxEvent(
                            tenant_id=tenant_id,
                            event_type="document.available.v1",
                            aggregate_type="Document",
                            aggregate_id=document_id,
                            payload={"version_id": str(version_id), "source": "legacy-backfill"},
                            created_at=created_at,
                        ),
                    ]
                )
                await session.commit()
            except Exception:
                await session.rollback()
                await run_in_threadpool(storage.delete, storage_key)
                raise
            imported += 1
            verified += 1
    return {"source": len(items), "imported": imported, "skipped": skipped, "verified": verified}


def main() -> None:
    parser = argparse.ArgumentParser(description="Import a verified Platform document export.")
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(backfill(args.input)), sort_keys=True))


if __name__ == "__main__":
    main()
