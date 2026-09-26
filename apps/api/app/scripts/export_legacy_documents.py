import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any

from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.db.session import async_session_factory
from app.models.document import Document
from app.services.storage import StorageError, storage_from_settings


async def export_documents(output: Path) -> dict[str, Any]:
    output = output.resolve()
    blobs = output / "blobs"
    blobs.mkdir(parents=True, exist_ok=True)
    settings = get_settings()
    storage = storage_from_settings(settings)
    async with async_session_factory() as session:
        documents = list(
            await session.scalars(select(Document).order_by(Document.created_at, Document.id))
        )
    manifest: list[dict[str, object]] = []
    for document in documents:
        try:
            content = await run_in_threadpool(storage.read_bytes, document.storage_key)
        except (FileNotFoundError, OSError, StorageError) as exc:
            raise RuntimeError(f"Legacy bytes are unavailable for {document.id}") from exc
        checksum = hashlib.sha256(content).hexdigest()
        if checksum != document.checksum_sha256:
            raise RuntimeError(f"Legacy checksum mismatch for {document.id}")
        blob_name = f"{document.id}.bin"
        (blobs / blob_name).write_bytes(content)
        manifest.append(
            {
                "id": str(document.id),
                "tenant_id": str(document.tenant_id),
                "resource_type": document.entity_type,
                "resource_id": str(document.entity_id),
                "category": document.category,
                "classification": "INTERNAL",
                "original_filename": document.original_filename,
                "content_type": document.content_type,
                "size_bytes": document.size_bytes,
                "checksum_sha256": checksum,
                "uploaded_by_user_id": str(document.uploaded_by_user_id),
                "created_at": document.created_at.isoformat(),
                "blob": f"blobs/{blob_name}",
            }
        )
    payload = {
        "format": "govcontrol-legacy-documents-v1",
        "count": len(manifest),
        "items": manifest,
    }
    (output / "manifest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Export legacy Platform documents safely.")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = asyncio.run(export_documents(args.output))
    print(json.dumps({"exported": result["count"], "output": str(args.output.resolve())}))


if __name__ == "__main__":
    main()
