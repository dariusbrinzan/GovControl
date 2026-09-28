import argparse
import asyncio
import json
import uuid
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.db.session import async_session_factory
from app.models.department import Department
from app.models.legal import (
    CourtDecision,
    EnforcementProceeding,
    LegalCase,
    LegalObligation,
    PenaltyRule,
)
from app.models.user import User
from app.services.penalties import PenaltyCalculationType, calculate_penalty_exposure


def date_time(value: date | datetime | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return datetime.combine(value, datetime.min.time(), UTC).isoformat()


def base_record(
    *,
    tenant_id: object,
    resource_type: str,
    source_id: object,
    source_url: str,
    source_event_at: datetime,
    **values: Any,
) -> dict[str, Any]:
    return {
        "tenant_id": str(tenant_id),
        "module": "legal" if resource_type not in {"user", "department"} else "platform",
        "resource_type": resource_type,
        "source_id": str(source_id),
        "source_url": source_url,
        "source_version": 1,
        "source_event_at": source_event_at.isoformat(),
        **{key: value for key, value in values.items() if value is not None},
    }


async def records(tenant_id: uuid.UUID | None = None) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    async with async_session_factory() as session:
        item: Any
        def scoped(model: Any) -> Any:
            statement = select(model)
            if tenant_id is not None:
                statement = statement.where(model.tenant_id == tenant_id)
            return statement.order_by(model.id)

        for item in await session.scalars(scoped(LegalCase)):
            output.append(
                base_record(
                    tenant_id=item.tenant_id,
                    resource_type="case",
                    source_id=item.id,
                    source_url=f"/legal/cases/{item.id}",
                    source_event_at=item.updated_at,
                    identifier=item.case_number,
                    display_label=item.court,
                    status=item.status.value,
                    occurred_at=date_time(item.filing_date) or item.created_at.isoformat(),
                    attributes={"court": item.court},
                )
            )
        for item in await session.scalars(scoped(CourtDecision)):
            output.append(
                base_record(
                    tenant_id=item.tenant_id,
                    resource_type="decision",
                    source_id=item.id,
                    source_url=f"/legal/decisions/{item.id}",
                    source_event_at=item.created_at,
                    identifier=item.decision_number,
                    display_label=item.decision_type,
                    occurred_at=date_time(item.decision_date),
                    attributes={"case_id": str(item.case_id)},
                )
            )
        for item in await session.scalars(scoped(LegalObligation)):
            output.append(
                base_record(
                    tenant_id=item.tenant_id,
                    resource_type="obligation",
                    source_id=item.id,
                    source_url=f"/legal/obligations/{item.id}",
                    source_event_at=item.updated_at,
                    identifier=f"OBL-{str(item.id)[:8].upper()}",
                    display_label=item.obligation_type.value,
                    status=item.status.value,
                    department_id=str(item.responsible_department_id)
                    if item.responsible_department_id
                    else None,
                    responsible_user_id=str(item.responsible_user_id)
                    if item.responsible_user_id
                    else None,
                    occurred_at=item.created_at.isoformat(),
                    due_at=date_time(item.due_date),
                    attributes={"decision_id": str(item.court_decision_id)},
                )
            )
        for item in await session.scalars(
            scoped(EnforcementProceeding)
        ):
            occurred = datetime.combine(item.start_date, datetime.min.time(), UTC)
            output.append(
                base_record(
                    tenant_id=item.tenant_id,
                    resource_type="enforcement",
                    source_id=item.id,
                    source_url=f"/legal/enforcements/{item.id}",
                    source_event_at=occurred,
                    identifier=item.file_number,
                    display_label="Procedură de executare",
                    status=item.status.value,
                    occurred_at=occurred.isoformat(),
                    attributes={"obligation_id": str(item.obligation_id)},
                )
            )
        for item in await session.scalars(scoped(PenaltyRule)):
            occurred = datetime.combine(item.start_date, datetime.min.time(), UTC)
            output.append(
                base_record(
                    tenant_id=item.tenant_id,
                    resource_type="penalty",
                    source_id=item.id,
                    source_url=f"/legal/penalties/{item.id}",
                    source_event_at=occurred,
                    identifier=f"PEN-{str(item.id)[:8].upper()}",
                    display_label=item.calculation_type,
                    occurred_at=occurred.isoformat(),
                    due_at=date_time(item.end_date),
                    amount=str(
                        calculate_penalty_exposure(
                            calculation_type=PenaltyCalculationType(item.calculation_type),
                            start_date=item.start_date,
                            as_of_date=date.today(),
                            daily_amount=item.daily_amount,
                            percentage=item.percentage,
                            base_value=item.base_value,
                            end_date=item.end_date,
                        )
                    ),
                    currency=item.currency,
                    attributes={"obligation_id": str(item.obligation_id)},
                )
            )
        for item in await session.scalars(scoped(Department)):
            output.append(
                base_record(
                    tenant_id=item.tenant_id,
                    resource_type="department",
                    source_id=item.id,
                    source_url=f"/platform/departments/{item.id}",
                    source_event_at=item.updated_at,
                    identifier=item.code or f"DEP-{str(item.id)[:8].upper()}",
                    display_label=item.name,
                    status="ACTIVE",
                    occurred_at=item.created_at.isoformat(),
                )
            )
        for item in await session.scalars(scoped(User)):
            output.append(
                base_record(
                    tenant_id=item.tenant_id,
                    resource_type="user",
                    source_id=item.id,
                    source_url=f"/platform/users/{item.id}",
                    source_event_at=item.updated_at,
                    identifier=f"USR-{str(item.id)[:8].upper()}",
                    display_label=item.display_name,
                    status="ACTIVE" if item.is_active else "INACTIVE",
                    department_id=str(item.department_id) if item.department_id else None,
                    occurred_at=item.created_at.isoformat(),
                )
            )
    return output


async def snapshot(tenant_id: uuid.UUID | None = None) -> dict[str, Any]:
    values = await records(tenant_id)
    return {
        "schema_version": 1,
        "source": "platform",
        "exported_at": datetime.now(UTC).isoformat(),
        "count": len(values),
        "records": values,
    }


async def export(path: Path) -> None:
    document = await snapshot()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, separators=(",", ":")), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export controlled Platform/GovLegal metadata")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    asyncio.run(export(args.output))


if __name__ == "__main__":
    main()
