import argparse
import asyncio
import hashlib
import json
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert

from insights_app.database import session_factory
from insights_app.models import (
    AuditEvent,
    BackfillState,
    OutboxEvent,
    ProjectionCheckpoint,
    ProjectionResource,
)
from insights_app.snapshot import ProjectionSnapshot, SnapshotRecord


def load_snapshot(path: Path) -> tuple[ProjectionSnapshot, str]:
    content = path.read_bytes()
    checksum = hashlib.sha256(content).hexdigest()
    return ProjectionSnapshot.model_validate_json(content), checksum


def values(record: SnapshotRecord) -> dict[str, Any]:
    return record.model_dump()


async def import_snapshot(
    snapshot: ProjectionSnapshot,
    checksum: str,
    *,
    rebuild: bool,
    batch_size: int,
    state_key: str | None = None,
) -> int:
    async with session_factory() as session:
        key = state_key or snapshot.source
        state = await session.get(BackfillState, key)
        if (
            state
            and state.checksum_sha256 == checksum
            and state.status == "SUCCEEDED"
            and not rebuild
        ):
            return 0
        if state is None or state.checksum_sha256 != checksum or rebuild:
            state = BackfillState(
                source=key,
                checksum_sha256=checksum,
                cursor=0,
                expected_count=snapshot.count,
                imported_count=0,
                status="RUNNING",
            )
            await session.merge(state)
            await session.commit()
            state = await session.get(BackfillState, key)
            assert state is not None
        if rebuild and state.cursor == 0:
            scopes = sorted({(record.tenant_id, record.module) for record in snapshot.records})
            for tenant_id, module in scopes:
                await session.execute(
                    delete(ProjectionResource).where(
                        ProjectionResource.tenant_id == tenant_id,
                        ProjectionResource.module == module,
                    )
                )
            await session.commit()

        imported = 0
        for start in range(int(state.cursor), snapshot.count, batch_size):
            batch = snapshot.records[start : start + batch_size]
            for record in batch:
                statement = insert(ProjectionResource).values(**values(record))
                incoming = statement.excluded
                statement = statement.on_conflict_do_update(
                    constraint="uq_projection_source",
                    set_={
                        "identifier": incoming.identifier,
                        "display_label": incoming.display_label,
                        "status": incoming.status,
                        "department_id": incoming.department_id,
                        "responsible_user_id": incoming.responsible_user_id,
                        "occurred_at": incoming.occurred_at,
                        "due_at": incoming.due_at,
                        "amount": incoming.amount,
                        "currency": incoming.currency,
                        "source_url": incoming.source_url,
                        "attributes": incoming.attributes,
                        "source_version": incoming.source_version,
                        "source_event_at": incoming.source_event_at,
                        "deleted": incoming.deleted,
                        "updated_at": func.now(),
                    },
                    where=incoming.source_version >= ProjectionResource.source_version,
                )
                await session.execute(statement)
            state.cursor = min(start + len(batch), snapshot.count)
            state.imported_count = state.cursor
            state.status = "RUNNING"
            state.last_error = None
            await session.commit()
            imported += len(batch)

        all_scopes = {(record.tenant_id, record.module) for record in snapshot.records}
        expected_by_scope = Counter(
            (record.tenant_id, record.module)
            for record in snapshot.records
            if not record.deleted
        )
        actual_by_scope: dict[tuple[uuid.UUID, str], int] = {}
        for tenant_id, module in all_scopes:
            actual_by_scope[(tenant_id, module)] = int(
                await session.scalar(
                    select(func.count())
                    .select_from(ProjectionResource)
                    .where(
                        ProjectionResource.tenant_id == tenant_id,
                        ProjectionResource.module == module,
                        ProjectionResource.deleted.is_(False),
                    )
                )
                or 0
            )
        mismatches = {
            f"{tenant_id}:{module}": {"expected": expected, "actual": actual_by_scope[scope]}
            for scope in all_scopes
            for tenant_id, module in (scope,)
            for expected in (expected_by_scope[scope],)
            if (rebuild and actual_by_scope[scope] != expected)
            or (not rebuild and actual_by_scope[scope] < expected)
        }
        if mismatches:
            state.status = "FAILED"
            state.last_error = "projection reconciliation failed"
            await session.commit()
            raise RuntimeError(f"projection reconciliation failed: {mismatches}")
        state.status = "SUCCEEDED"
        checkpoint = await session.get(ProjectionCheckpoint, "backfill")
        if checkpoint is None:
            checkpoint = ProjectionCheckpoint(
                consumer="backfill",
                last_stream_id="snapshot",
                last_event_at=snapshot.exported_at,
                last_processed_at=datetime.now(UTC),
                last_heartbeat_at=datetime.now(UTC),
                processed_count=snapshot.count,
                failed_count=0,
                projection_version=snapshot.count,
            )
            session.add(checkpoint)
        else:
            checkpoint.last_event_at = snapshot.exported_at
            checkpoint.last_processed_at = datetime.now(UTC)
            checkpoint.last_heartbeat_at = checkpoint.last_processed_at
            checkpoint.processed_count += snapshot.count
            checkpoint.projection_version += snapshot.count
        tenant_ids = sorted({record.tenant_id for record in snapshot.records}, key=str)
        for tenant_id in tenant_ids:
            tenant_scopes = {
                module: {
                    "expected": expected_by_scope[(scoped_tenant, module)],
                    "actual": actual_by_scope[(scoped_tenant, module)],
                }
                for scoped_tenant, module in all_scopes
                if scoped_tenant == tenant_id
            }
            event_id = uuid.uuid5(
                uuid.NAMESPACE_URL,
                (
                    f"govinsights:{snapshot.source}:{checksum}:{tenant_id}:"
                    f"{'rebuild' if rebuild else 'backfill'}"
                ),
            )
            session.add(
                AuditEvent(
                    tenant_id=tenant_id,
                    actor_user_id=None,
                    action="projection.rebuilt" if rebuild else "projection.backfilled",
                    entity_type="snapshot",
                    entity_id=event_id,
                    payload={"source": snapshot.source, "scopes": tenant_scopes},
                )
            )
            session.add(
                OutboxEvent(
                    tenant_id=tenant_id,
                    event_type="insights.projection_rebuilt.v1",
                    aggregate_id=event_id,
                    payload={"source": snapshot.source, "scopes": tenant_scopes},
                )
            )
        await session.commit()
        return imported


async def run(paths: list[Path], rebuild: bool, batch_size: int) -> None:
    for path in paths:
        snapshot, checksum = load_snapshot(path)
        imported = await import_snapshot(snapshot, checksum, rebuild=rebuild, batch_size=batch_size)
        print(
            json.dumps({"source": snapshot.source, "records": snapshot.count, "imported": imported})
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Idempotent GovInsights snapshot backfill")
    parser.add_argument("--input", action="append", required=True, type=Path)
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--batch-size", type=int, default=200, choices=range(1, 1001))
    args = parser.parse_args()
    asyncio.run(run(args.input, args.rebuild, args.batch_size))


if __name__ == "__main__":
    main()
