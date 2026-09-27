import csv
import hashlib
import io
from datetime import UTC, datetime
from typing import Any

from openpyxl import Workbook  # type: ignore[import-untyped]
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from insights_app.config import Settings
from insights_app.models import ExportArtifact, OutboxEvent, ReportRun, SavedReport
from insights_app.service import report_query
from insights_app.storage import ExportStorage


def safe_cell(value: Any) -> Any:
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return f"'{value}"
    return value


def render_csv(columns: list[str], rows: list[list[Any]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(columns)
    writer.writerows([[safe_cell(value) for value in row] for row in rows])
    return stream.getvalue().encode("utf-8-sig")


def render_xlsx(columns: list[str], rows: list[list[Any]]) -> bytes:
    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet("GovInsights")
    sheet.append(columns)
    for row in rows:
        sheet.append([safe_cell(value) for value in row])
    stream = io.BytesIO()
    workbook.save(stream)
    return stream.getvalue()


async def process_export(
    session: AsyncSession, storage: ExportStorage, artifact: ExportArtifact, settings: Settings
) -> None:
    run = await session.get(ReportRun, artifact.run_id)
    report = await session.get(SavedReport, run.report_id) if run else None
    if run is None or report is None or run.tenant_id != artifact.tenant_id:
        artifact.status = "FAILED"
        if run:
            run.status = "FAILED"
            run.error_code = "REPORT_NOT_FOUND"
        await session.commit()
        return
    run.status = "RUNNING"
    run.started_at = datetime.now(UTC)
    artifact.status = "RUNNING"
    await session.commit()
    resources = list(
        (
            await session.scalars(
                report_query(report, artifact.tenant_id).limit(settings.export_max_rows + 1)
            )
        ).all()
    )
    if len(resources) > settings.export_max_rows:
        run.status = artifact.status = "FAILED"
        run.error_code = "ROW_LIMIT_EXCEEDED"
        run.completed_at = datetime.now(UTC)
        await session.commit()
        return
    rows = [[getattr(resource, column) for column in report.columns] for resource in resources]
    if artifact.format == "csv":
        data = render_csv(report.columns, rows)
        content_type = "text/csv; charset=utf-8"
    else:
        data = render_xlsx(report.columns, rows)
        content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    key = f"{artifact.tenant_id}/{artifact.owner_user_id}/{artifact.id}.{artifact.format}"
    await storage.put(key, data, content_type)
    artifact.storage_key = key
    artifact.content_type = content_type
    artifact.size_bytes = len(data)
    artifact.checksum_sha256 = hashlib.sha256(data).hexdigest()
    artifact.status = "SUCCEEDED"
    run.status = "SUCCEEDED"
    run.row_count = len(rows)
    run.completed_at = datetime.now(UTC)
    session.add(
        OutboxEvent(
            tenant_id=artifact.tenant_id,
            event_type="insights.export_ready.v1",
            aggregate_id=artifact.id,
            payload={"run_id": str(run.id), "format": artifact.format},
        )
    )
    await session.commit()


async def next_exports(session: AsyncSession, limit: int) -> list[ExportArtifact]:
    result = await session.scalars(
        select(ExportArtifact)
        .where(ExportArtifact.status == "QUEUED")
        .order_by(ExportArtifact.created_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    return list(result.all())
