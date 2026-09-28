import argparse
import asyncio
import json
import uuid
from pathlib import Path

from sqlalchemy import delete, select

from insights_app.config import get_settings
from insights_app.database import session_factory
from insights_app.models import AuditEvent, ExportArtifact, OutboxEvent, ReportRun, SavedReport
from insights_app.storage import create_storage


async def cleanup(path: Path) -> dict[str, int]:
    payload = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    report_ids = [uuid.UUID(value) for value in payload.get("report_ids", [])]
    run_ids = [uuid.UUID(value) for value in payload.get("run_ids", [])]
    export_ids = [uuid.UUID(value) for value in payload.get("export_ids", [])]
    storage = create_storage(get_settings())
    objects = 0
    async with session_factory() as session:
        # The prefix fallback also cleans interrupted tests that failed before writing the
        # manifest. It deliberately targets only names created by the live E2E suite.
        prefix_report_ids = list(
            (
                await session.scalars(
                    select(SavedReport.id).where(SavedReport.name.like("E2E GovInsights %"))
                )
            ).all()
        )
        report_ids = list(set(report_ids) | set(prefix_report_ids))
        if report_ids:
            discovered_run_ids = list(
                (
                    await session.scalars(
                        select(ReportRun.id).where(ReportRun.report_id.in_(report_ids))
                    )
                ).all()
            )
            run_ids = list(set(run_ids) | set(discovered_run_ids))
        if run_ids:
            discovered_export_ids = list(
                (
                    await session.scalars(
                        select(ExportArtifact.id).where(ExportArtifact.run_id.in_(run_ids))
                    )
                ).all()
            )
            export_ids = list(set(export_ids) | set(discovered_export_ids))
        entity_ids = [*report_ids, *run_ids, *export_ids]
        artifacts = list(
            (
                await session.scalars(
                    select(ExportArtifact).where(ExportArtifact.id.in_(export_ids))
                )
            ).all()
        )
        for artifact in artifacts:
            if artifact.storage_key:
                try:
                    await storage.delete(artifact.storage_key)
                except FileNotFoundError:
                    pass
                objects += 1
        if entity_ids:
            await session.execute(delete(AuditEvent).where(AuditEvent.entity_id.in_(entity_ids)))
            await session.execute(
                delete(OutboxEvent).where(OutboxEvent.aggregate_id.in_(entity_ids))
            )
        await session.execute(delete(ExportArtifact).where(ExportArtifact.id.in_(export_ids)))
        await session.execute(delete(ReportRun).where(ReportRun.id.in_(run_ids)))
        await session.execute(delete(SavedReport).where(SavedReport.id.in_(report_ids)))
        await session.commit()
    path.unlink(missing_ok=True)
    return {
        "reports": len(report_ids),
        "runs": len(run_ids),
        "exports": len(export_ids),
        "objects": objects,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Remove GovInsights live E2E artifacts")
    parser.add_argument(
        "--manifest", type=Path, default=Path("/tmp/govcontrol-insights-e2e.json")
    )
    args = parser.parse_args()
    print(json.dumps(asyncio.run(cleanup(args.manifest)), sort_keys=True))


if __name__ == "__main__":
    main()
