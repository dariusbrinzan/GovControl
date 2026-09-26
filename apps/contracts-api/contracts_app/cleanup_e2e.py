import asyncio
import json
import uuid
from datetime import datetime
from pathlib import Path

from sqlalchemy import delete

from contracts_app.config import get_settings
from contracts_app.database import session_factory
from contracts_app.models import ContractAuditEvent, OutboxEvent

FIXTURE_PATH = Path("/tmp/govcontrol-notifications-e2e.json")


async def cleanup(path: Path = FIXTURE_PATH) -> dict[str, int]:
    settings = get_settings()
    if settings.app_env != "development":
        raise RuntimeError("E2E cleanup is allowed only in development.")
    if not path.exists():
        return {"audit": 0, "outbox": 0}
    payload = json.loads(path.read_text(encoding="utf-8"))
    started_at = datetime.fromisoformat(str(payload["started_at"]).replace("Z", "+00:00"))
    resource_ids = [uuid.UUID(value) for value in payload.get("contract_ids", [])]
    async with session_factory() as session:
        audit = await session.scalars(
            delete(ContractAuditEvent).where(
                ContractAuditEvent.entity_id.in_(resource_ids),
                ContractAuditEvent.created_at >= started_at,
            ).returning(ContractAuditEvent.id)
        )
        outbox = await session.scalars(
            delete(OutboxEvent).where(
                OutboxEvent.aggregate_id.in_(resource_ids),
                OutboxEvent.created_at >= started_at,
            ).returning(OutboxEvent.id)
        )
        audit_count = len(audit.all())
        outbox_count = len(outbox.all())
        await session.commit()
    return {"audit": audit_count, "outbox": outbox_count}


def main() -> None:
    print(json.dumps(asyncio.run(cleanup()), sort_keys=True))


if __name__ == "__main__":
    main()
