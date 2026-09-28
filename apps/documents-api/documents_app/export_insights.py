import argparse
import asyncio
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from documents_app.database import session_factory
from documents_app.models import Document, DocumentVersion


def enum_value(value: object) -> str:
    return str(getattr(value, "value", value))


async def records(tenant_id: uuid.UUID | None = None) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    async with session_factory() as session:
        statement = select(Document)
        if tenant_id is not None:
            statement = statement.where(Document.tenant_id == tenant_id)
        documents = await session.scalars(statement.order_by(Document.id))
        for item in documents:
            version = await session.scalar(
                select(DocumentVersion).where(
                    DocumentVersion.document_id == item.id,
                    DocumentVersion.version_number == item.current_version_number,
                )
            )
            output.append(
                {
                    "tenant_id": str(item.tenant_id),
                    "module": "documents",
                    "resource_type": "document",
                    "source_id": str(item.id),
                    "identifier": f"DOC-{str(item.id)[:8].upper()}",
                    "display_label": version.safe_filename if version else item.category,
                    "status": "ARCHIVED" if item.archived_at else enum_value(item.state),
                    "responsible_user_id": str(item.created_by_user_id),
                    "occurred_at": item.created_at.isoformat(),
                    "due_at": datetime.combine(
                        item.retention_until, datetime.min.time(), UTC
                    ).isoformat()
                    if item.retention_until
                    else None,
                    "source_url": f"/legal/documents/{item.id}",
                    "attributes": {
                        "category": item.category,
                        "version": item.current_version_number,
                    },
                    "source_version": item.lock_version,
                    "source_event_at": item.updated_at.isoformat(),
                    "deleted": item.deleted_at is not None,
                }
            )
    return output


async def snapshot(tenant_id: uuid.UUID | None = None) -> dict[str, object]:
    values = await records(tenant_id)
    return {
        "schema_version": 1,
        "source": "documents",
        "exported_at": datetime.now(UTC).isoformat(),
        "count": len(values),
        "records": values,
    }


async def export(path: Path) -> None:
    document = await snapshot()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, separators=(",", ":")), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export controlled GovDocuments metadata")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    asyncio.run(export(args.output))


if __name__ == "__main__":
    main()
