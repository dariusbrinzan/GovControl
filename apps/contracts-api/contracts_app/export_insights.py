import argparse
import asyncio
import json
import uuid
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select

from contracts_app.database import session_factory
from contracts_app.models import (
    Contract,
    ContractMilestone,
    ContractObligation,
    ContractPayment,
)


def date_time(value: date | datetime | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return datetime.combine(value, datetime.min.time(), UTC).isoformat()


def record(item: Any, resource_type: str, contract_id: object, **values: Any) -> dict[str, Any]:
    event_at = getattr(item, "updated_at", None) or getattr(item, "created_at", None)
    if event_at is None:
        event_at = datetime.now(UTC)
    return {
        "tenant_id": str(item.tenant_id),
        "module": "contracts",
        "resource_type": resource_type,
        "source_id": str(item.id),
        "source_url": f"/contracts/{contract_id}",
        "source_version": 1,
        "source_event_at": event_at.isoformat(),
        **{key: value for key, value in values.items() if value is not None},
    }


async def records(tenant_id: uuid.UUID | None = None) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    async with session_factory() as session:
        item: Any
        def scoped(model: Any) -> Any:
            statement = select(model)
            if tenant_id is not None:
                statement = statement.where(model.tenant_id == tenant_id)
            return statement.order_by(model.id)

        for item in await session.scalars(scoped(Contract)):
            output.append(
                record(
                    item,
                    "contract",
                    item.id,
                    identifier=item.contract_number,
                    display_label=item.title,
                    status=item.status.value,
                    department_id=str(item.responsible_department_id)
                    if item.responsible_department_id
                    else None,
                    responsible_user_id=str(item.responsible_user_id)
                    if item.responsible_user_id
                    else None,
                    occurred_at=date_time(item.start_date),
                    due_at=date_time(item.end_date),
                    amount=str(item.value),
                    currency=item.currency.upper(),
                )
            )
        for item in await session.scalars(scoped(ContractMilestone)):
            output.append(
                record(
                    item,
                    "milestone",
                    item.contract_id,
                    identifier=f"MS-{str(item.id)[:8].upper()}",
                    display_label=item.title,
                    status=item.status.value,
                    due_at=date_time(item.due_date),
                    attributes={"contract_id": str(item.contract_id)},
                )
            )
        for item in await session.scalars(
            scoped(ContractObligation)
        ):
            output.append(
                record(
                    item,
                    "contract_obligation",
                    item.contract_id,
                    identifier=f"COB-{str(item.id)[:8].upper()}",
                    display_label="Obligație contractuală",
                    status=item.status.value,
                    responsible_user_id=str(item.responsible_user_id)
                    if item.responsible_user_id
                    else None,
                    due_at=date_time(item.due_date),
                    attributes={"contract_id": str(item.contract_id)},
                )
            )
        for item in await session.scalars(scoped(ContractPayment)):
            output.append(
                record(
                    item,
                    "payment",
                    item.contract_id,
                    identifier=item.reference or f"PAY-{str(item.id)[:8].upper()}",
                    display_label="Plată contractuală",
                    status=item.status.value,
                    occurred_at=date_time(item.paid_date),
                    due_at=date_time(item.due_date),
                    amount=str(item.amount),
                    currency=item.currency.upper(),
                    attributes={"contract_id": str(item.contract_id)},
                )
            )
    return output


async def snapshot(tenant_id: uuid.UUID | None = None) -> dict[str, Any]:
    values = await records(tenant_id)
    return {
        "schema_version": 1,
        "source": "contracts",
        "exported_at": datetime.now(UTC).isoformat(),
        "count": len(values),
        "records": values,
    }


async def export(path: Path) -> None:
    document = await snapshot()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, separators=(",", ":")), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export controlled GovContracts metadata")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    asyncio.run(export(args.output))


if __name__ == "__main__":
    main()
