import argparse
import asyncio
import json
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select

from contracts_app.database import session_factory
from contracts_app.models import (
    Contract,
    ContractMilestone,
    ContractNotification,
    ContractObligation,
    ContractPayment,
)


async def recipient_for(
    tenant_id: uuid.UUID, entity_type: str, entity_id: uuid.UUID
) -> uuid.UUID | None:
    async with session_factory() as session:
        statement: Any
        if entity_type == "ContractMilestone":
            statement = (
                select(Contract.responsible_user_id, Contract.created_by)
                .join(ContractMilestone, ContractMilestone.contract_id == Contract.id)
                .where(
                    ContractMilestone.id == entity_id,
                    ContractMilestone.tenant_id == tenant_id,
                )
            )
        elif entity_type == "ContractObligation":
            statement = (
                select(
                    ContractObligation.responsible_user_id,
                    Contract.responsible_user_id,
                    Contract.created_by,
                )
                .join(Contract, Contract.id == ContractObligation.contract_id)
                .where(
                    ContractObligation.id == entity_id,
                    ContractObligation.tenant_id == tenant_id,
                )
            )
        elif entity_type == "ContractPayment":
            statement = (
                select(Contract.responsible_user_id, Contract.created_by)
                .join(ContractPayment, ContractPayment.contract_id == Contract.id)
                .where(
                    ContractPayment.id == entity_id,
                    ContractPayment.tenant_id == tenant_id,
                )
            )
        else:
            statement = select(Contract.responsible_user_id, Contract.created_by).where(
                Contract.id == entity_id, Contract.tenant_id == tenant_id
            )
        row = (await session.execute(statement)).one_or_none()
    if row is None:
        return None
    return next((value for value in row if value is not None), None)


async def export(output: Path) -> tuple[int, int]:
    async with session_factory() as session:
        rows = list(
            await session.scalars(
                select(ContractNotification).order_by(ContractNotification.created_at)
            )
        )
    payload: list[dict[str, object]] = []
    unresolved = 0
    for item in rows:
        recipient_id = await recipient_for(item.tenant_id, item.entity_type, item.entity_id)
        if recipient_id is None:
            unresolved += 1
            continue
        payload.append(
            {
                "source": "contracts",
                "legacy_id": str(item.id),
                "tenant_id": str(item.tenant_id),
                "recipient_user_id": str(recipient_id),
                "resource_type": item.entity_type,
                "resource_id": str(item.entity_id),
                "category": "CONTRACTS",
                "severity": "WARNING",
                "title": item.title,
                "body": item.body,
                "status": "READ" if item.read_at else "UNREAD",
                "read_at": item.read_at.isoformat() if item.read_at else None,
                "created_at": item.created_at.isoformat(),
            }
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(payload), unresolved


def main() -> None:
    parser = argparse.ArgumentParser(description="Export legacy GovContracts notifications.")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    count, unresolved = asyncio.run(export(args.output))
    print(json.dumps({"source": "contracts", "exported": count, "unresolved": unresolved}))


if __name__ == "__main__":
    main()
