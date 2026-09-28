import asyncio
import csv
import hashlib
import io
from datetime import UTC, datetime
from typing import Any

from openpyxl import Workbook  # type: ignore[import-untyped]
from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from insights_app.config import Settings
from insights_app.models import AuditEvent, ExportArtifact, OutboxEvent, ReportRun, SavedReport
from insights_app.service import report_query
from insights_app.storage import ExportStorage


class ExportLimitError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


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
    artifact_id = artifact.id
    run_id = artifact.run_id
    run = await session.get(ReportRun, artifact.run_id)
    report = await session.get(SavedReport, run.report_id) if run else None
    if run is None or report is None or run.tenant_id != artifact.tenant_id:
        artifact.status = "FAILED"
        if run:
            run.status = "FAILED"
            run.error_code = "REPORT_NOT_FOUND"
            run.completed_at = datetime.now(UTC)
            session.add(
                OutboxEvent(
                    tenant_id=run.tenant_id,
                    event_type="insights.report_failed.v1",
                    aggregate_id=run.id,
                    payload={"error_code": run.error_code},
                )
            )
        await session.commit()
        return
    run.status = "RUNNING"
    run.started_at = datetime.now(UTC)
    artifact.status = "RUNNING"
    await session.commit()
    try:
        async with asyncio.timeout(settings.export_timeout_seconds):
            resources = list(
                (
                    await session.scalars(
                        report_query(report, artifact.tenant_id).limit(
                            settings.export_max_rows + 1
                        )
                    )
                ).all()
            )
            if len(resources) > settings.export_max_rows:
                raise ExportLimitError("ROW_LIMIT_EXCEEDED")
            rows = [
                [getattr(resource, column) for column in report.columns]
                for resource in resources
            ]
            if artifact.format == "csv":
                data = render_csv(report.columns, rows)
                content_type = "text/csv; charset=utf-8"
            else:
                data = render_xlsx(report.columns, rows)
                content_type = (
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            if len(data) > settings.export_max_bytes:
                raise ExportLimitError("SIZE_LIMIT_EXCEEDED")
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
                event_type="insights.report_completed.v1",
                aggregate_id=run.id,
                payload={"row_count": len(rows)},
            )
        )
        session.add(
            OutboxEvent(
                tenant_id=artifact.tenant_id,
                event_type="insights.export_ready.v1",
                aggregate_id=artifact.id,
                payload={"run_id": str(run.id), "format": artifact.format},
            )
        )
        await session.commit()
    except Exception as exc:
        await session.rollback()
        failed_artifact = await session.get(ExportArtifact, artifact_id)
        failed_run = await session.get(ReportRun, run_id)
        if failed_artifact is not None:
            failed_artifact.status = "FAILED"
        if failed_run is not None:
            failed_run.status = "FAILED"
            if isinstance(exc, ExportLimitError):
                failed_run.error_code = exc.code
            elif isinstance(exc, TimeoutError):
                failed_run.error_code = "TIME_LIMIT_EXCEEDED"
            else:
                failed_run.error_code = "EXPORT_FAILED"
            failed_run.completed_at = datetime.now(UTC)
            session.add(
                OutboxEvent(
                    tenant_id=failed_run.tenant_id,
                    event_type="insights.report_failed.v1",
                    aggregate_id=failed_run.id,
                    payload={"error_code": failed_run.error_code},
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


async def cleanup_expired_exports(
    session: AsyncSession, storage: ExportStorage, now: datetime, limit: int = 100
) -> int:
    artifacts = list(
        (
            await session.scalars(
                select(ExportArtifact)
                .where(ExportArtifact.expires_at <= now)
                .order_by(ExportArtifact.expires_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        ).all()
    )
    for artifact in artifacts:
        if artifact.storage_key:
            try:
                await storage.delete(artifact.storage_key)
            except FileNotFoundError:
                pass
        session.add(
            AuditEvent(
                tenant_id=artifact.tenant_id,
                action="export.expired",
                entity_type="export",
                entity_id=artifact.id,
                payload={"format": artifact.format},
            )
        )
        await session.delete(artifact)
    await session.commit()
    return len(artifacts)


async def process_report_run(session: AsyncSession, run: ReportRun, settings: Settings) -> None:
    report = await session.get(SavedReport, run.report_id)
    run.started_at = datetime.now(UTC)
    if report is None or report.tenant_id != run.tenant_id:
        run.status = "FAILED"
        run.error_code = "REPORT_NOT_FOUND"
        row_count = None
    else:
        run.status = "RUNNING"
        await session.flush()
        try:
            async with asyncio.timeout(settings.export_timeout_seconds):
                row_count = int(
                    await session.scalar(
                        select(func.count()).select_from(
                            report_query(report, run.tenant_id)
                            .limit(settings.export_max_rows + 1)
                            .subquery()
                        )
                    )
                    or 0
                )
        except TimeoutError:
            run.status = "FAILED"
            run.error_code = "TIME_LIMIT_EXCEEDED"
            row_count = None
        else:
            if row_count > settings.export_max_rows:
                run.status = "FAILED"
                run.error_code = "ROW_LIMIT_EXCEEDED"
            else:
                run.status = "SUCCEEDED"
                run.row_count = row_count
    run.completed_at = datetime.now(UTC)
    session.add(
        OutboxEvent(
            tenant_id=run.tenant_id,
            event_type=(
                "insights.report_completed.v1"
                if run.status == "SUCCEEDED"
                else "insights.report_failed.v1"
            ),
            aggregate_id=run.id,
            payload={
                **({"row_count": row_count} if row_count is not None else {}),
                **({"error_code": run.error_code} if run.error_code else {}),
            },
        )
    )
    await session.commit()


async def next_report_runs(session: AsyncSession, limit: int) -> list[ReportRun]:
    has_export = exists().where(ExportArtifact.run_id == ReportRun.id)
    result = await session.scalars(
        select(ReportRun)
        .where(ReportRun.status == "QUEUED", ~has_export)
        .order_by(ReportRun.requested_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    return list(result.all())
