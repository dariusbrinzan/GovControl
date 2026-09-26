import argparse
import asyncio
import json
from pathlib import Path

from sqlalchemy import select

from app.db.session import async_session_factory
from app.models.notification import Notification


async def export(output: Path) -> int:
    async with async_session_factory() as session:
        rows = list(await session.scalars(select(Notification).order_by(Notification.created_at)))
    payload = [
        {
            "source": "platform",
            "legacy_id": str(item.id),
            "tenant_id": str(item.tenant_id),
            "recipient_user_id": str(item.recipient_user_id),
            "resource_type": item.entity_type,
            "resource_id": str(item.entity_id),
            "category": "LEGAL",
            "severity": "WARNING",
            "title": item.title,
            "body": item.body,
            "status": str(item.status),
            "read_at": item.read_at.isoformat() if item.read_at else None,
            "created_at": item.created_at.isoformat(),
        }
        for item in rows
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(payload)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export legacy Platform notifications.")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    count = asyncio.run(export(args.output))
    print(json.dumps({"source": "platform", "exported": count}))


if __name__ == "__main__":
    main()
