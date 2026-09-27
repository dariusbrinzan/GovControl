import uuid
from datetime import UTC, date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from insights_app.config import Settings, get_settings
from insights_app.database import get_session
from insights_app.models import AuditEvent, ExportArtifact, ProjectionCheckpoint, ReportRun
from insights_app.observability import current_request_id
from insights_app.schemas import (
    MODULES,
    REPORT_COLUMNS,
    DashboardFilter,
    DashboardResponse,
    ExportResponse,
    ProjectionStatusResponse,
    ReportCreate,
    ReportResponse,
    RunRequest,
    RunResponse,
    SearchPage,
    UserContext,
)
from insights_app.security import require_permission
from insights_app.service import (
    create_report,
    dashboard,
    list_reports,
    queue_report_run,
    remove_report,
    replace_report,
    search_resources,
)

router = APIRouter(prefix="/insights")
Session = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
Reader = Annotated[UserContext, Depends(require_permission("insights.read"))]
Searcher = Annotated[UserContext, Depends(require_permission("insights.search"))]
Reporter = Annotated[UserContext, Depends(require_permission("insights.report"))]
Exporter = Annotated[UserContext, Depends(require_permission("insights.export"))]
Admin = Annotated[UserContext, Depends(require_permission("insights.admin"))]


def filters_from_query(
    date_from: date | None,
    date_to: date | None,
    department_id: uuid.UUID | None,
    responsible_user_id: uuid.UUID | None,
) -> DashboardFilter:
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "date_from must precede date_to")
    return DashboardFilter(
        date_from=date_from,
        date_to=date_to,
        department_id=department_id,
        responsible_user_id=responsible_user_id,
    )


@router.get("/dashboards/executive", response_model=DashboardResponse)
async def executive_dashboard(
    user: Reader,
    session: Session,
    settings: SettingsDep,
    date_from: date | None = None,
    date_to: date | None = None,
    department_id: uuid.UUID | None = None,
    responsible_user_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    return await dashboard(
        session,
        user.tenant_id,
        filters_from_query(date_from, date_to, department_id, responsible_user_id),
        settings,
    )


@router.get("/dashboards/{module}", response_model=DashboardResponse)
async def module_dashboard(
    module: str,
    user: Reader,
    session: Session,
    settings: SettingsDep,
    date_from: date | None = None,
    date_to: date | None = None,
    department_id: uuid.UUID | None = None,
    responsible_user_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    if module not in MODULES:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown GovControl module.")
    return await dashboard(
        session,
        user.tenant_id,
        filters_from_query(date_from, date_to, department_id, responsible_user_id),
        settings,
        module,
    )


@router.get("/search", response_model=SearchPage)
async def unified_search(
    user: Searcher,
    session: Session,
    q: Annotated[str, Query(min_length=2, max_length=200)],
    module: str | None = None,
    resource_type: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status", max_length=80)] = None,
    responsible_user_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0, le=100000)] = 0,
) -> dict[str, Any]:
    if module and module not in MODULES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unsupported module filter.")
    items, total = await search_resources(
        session,
        user.tenant_id,
        q,
        module,
        resource_type,
        status_filter,
        responsible_user_id,
        date_from,
        date_to,
        limit,
        offset,
    )
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/metadata")
async def metadata(_: Reader) -> dict[str, list[str]]:
    return {"modules": sorted(MODULES), "report_columns": sorted(REPORT_COLUMNS)}


@router.get("/reports", response_model=list[ReportResponse])
async def reports(user: Reporter, session: Session) -> list[Any]:
    return await list_reports(session, user)


@router.post("/reports", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
async def save_report(payload: ReportCreate, user: Reporter, session: Session) -> Any:
    return await create_report(session, user, payload)


@router.put("/reports/{report_id}", response_model=ReportResponse)
async def update_report(
    report_id: uuid.UUID, payload: ReportCreate, user: Reporter, session: Session
) -> Any:
    try:
        return await replace_report(session, user, report_id, payload)
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report not found.") from exc
    except PermissionError as exc:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Only the owner can change this report."
        ) from exc


@router.delete("/reports/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_report(report_id: uuid.UUID, user: Reporter, session: Session) -> Response:
    try:
        await remove_report(session, user, report_id)
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report not found.") from exc
    except PermissionError as exc:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Only the owner can delete this report."
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/reports/{report_id}/runs", response_model=RunResponse, status_code=status.HTTP_202_ACCEPTED
)
async def run_report(
    report_id: uuid.UUID,
    payload: RunRequest,
    user: Reporter,
    session: Session,
    settings: SettingsDep,
) -> Any:
    if payload.export_format and "insights.export" not in user.permissions:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Export permission is required.")
    try:
        run, _ = await queue_report_run(session, user, report_id, payload.export_format, settings)
        return run
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report not found.") from exc


@router.get("/runs", response_model=list[RunResponse])
async def runs(
    user: Reporter, session: Session, limit: Annotated[int, Query(ge=1, le=100)] = 50
) -> list[Any]:
    result = await session.scalars(
        select(ReportRun)
        .where(ReportRun.tenant_id == user.tenant_id)
        .order_by(ReportRun.requested_at.desc())
        .limit(limit)
    )
    return list(result.all())


@router.get("/exports", response_model=list[ExportResponse])
async def exports(
    user: Exporter, session: Session, limit: Annotated[int, Query(ge=1, le=100)] = 50
) -> list[Any]:
    statement = select(ExportArtifact).where(ExportArtifact.tenant_id == user.tenant_id)
    if "insights.admin" not in user.permissions:
        statement = statement.where(ExportArtifact.owner_user_id == user.id)
    result = await session.scalars(
        statement.order_by(ExportArtifact.created_at.desc()).limit(limit)
    )
    return list(result.all())


@router.get("/exports/{export_id}/download")
async def download_export(
    export_id: uuid.UUID, request: Request, user: Exporter, session: Session
) -> Response:
    artifact = await session.get(ExportArtifact, export_id)
    if (
        artifact is None
        or artifact.tenant_id != user.tenant_id
        or (artifact.owner_user_id != user.id and "insights.admin" not in user.permissions)
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Export not found.")
    if artifact.status != "SUCCEEDED" or not artifact.storage_key:
        raise HTTPException(status.HTTP_409_CONFLICT, "Export is not ready.")
    if artifact.expires_at <= datetime.now(UTC):
        raise HTTPException(status.HTTP_410_GONE, "Export has expired.")
    try:
        content = await request.app.state.export_storage.get(artifact.storage_key)
    except FileNotFoundError as exc:
        raise HTTPException(status.HTTP_410_GONE, "Export is no longer available.") from exc
    session.add(
        AuditEvent(
            tenant_id=user.tenant_id,
            actor_user_id=user.id,
            action="export.downloaded",
            entity_type="export",
            entity_id=artifact.id,
            request_id=current_request_id(),
            payload={"format": artifact.format},
        )
    )
    await session.commit()
    filename = f"govinsights-{artifact.id}.{artifact.format}"
    return Response(
        content=content,
        media_type=artifact.content_type or "application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-SHA256": artifact.checksum_sha256 or "",
        },
    )


@router.get("/projections/status", response_model=ProjectionStatusResponse)
async def projection_status(_: Reader, session: Session, settings: SettingsDep) -> dict[str, Any]:
    checkpoint = await session.get(ProjectionCheckpoint, settings.consumer_group)
    if checkpoint is None:
        return {
            "consumer": settings.consumer_group,
            "last_stream_id": "0-0",
            "last_event_at": None,
            "last_processed_at": None,
            "processed_count": 0,
            "failed_count": 0,
            "projection_version": 0,
            "stale": True,
            "lag": None,
        }
    from datetime import timedelta

    stale = checkpoint.last_processed_at is None or checkpoint.last_processed_at < datetime.now(
        UTC
    ) - timedelta(seconds=settings.projection_stale_seconds)
    return {
        **{
            column: getattr(checkpoint, column)
            for column in (
                "consumer",
                "last_stream_id",
                "last_event_at",
                "last_processed_at",
                "processed_count",
                "failed_count",
                "projection_version",
            )
        },
        "stale": stale,
        "lag": None,
    }


@router.post("/projections/rebuild", status_code=status.HTTP_202_ACCEPTED)
async def request_rebuild(_: Admin) -> dict[str, str]:
    return {
        "status": "accepted",
        "detail": "Use the idempotent backfill command to rebuild projections.",
    }
