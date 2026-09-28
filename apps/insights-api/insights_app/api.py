import hashlib
import json
import uuid
from datetime import UTC, date, datetime
from typing import Annotated, Any, Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from insights_app.backfill import import_snapshot
from insights_app.config import Settings, get_settings
from insights_app.database import get_session
from insights_app.models import AuditEvent, ExportArtifact, ProjectionCheckpoint
from insights_app.observability import current_request_id
from insights_app.schemas import (
    MODULES,
    REPORT_COLUMNS,
    REPORT_RESOURCE_TYPES,
    AuditResponse,
    DashboardFilter,
    DashboardResponse,
    DeadLetterResponse,
    EventEnvelope,
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
    list_report_runs,
    list_reports,
    queue_report_run,
    remove_report,
    replace_report,
    search_resources,
)
from insights_app.snapshot import ProjectionSnapshot

router = APIRouter(prefix="/insights")
Session = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
Reader = Annotated[UserContext, Depends(require_permission("insights.read"))]
Searcher = Annotated[UserContext, Depends(require_permission("insights.search"))]
Reporter = Annotated[UserContext, Depends(require_permission("insights.report"))]
Exporter = Annotated[UserContext, Depends(require_permission("insights.export"))]
Admin = Annotated[UserContext, Depends(require_permission("insights.admin"))]
Auditor = Annotated[UserContext, Depends(require_permission("insights.audit"))]


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


async def _cached_dashboard(
    request: Request,
    session: AsyncSession,
    user: UserContext,
    filters: DashboardFilter,
    settings: Settings,
    module: str | None,
) -> dict[str, Any]:
    checkpoint = await session.get(ProjectionCheckpoint, settings.consumer_group)
    projection_version = checkpoint.projection_version if checkpoint else 0
    cache_input = json.dumps(
        {"module": module, **filters.model_dump(mode="json")},
        sort_keys=True,
        separators=(",", ":"),
    )
    filter_hash = hashlib.sha256(cache_input.encode()).hexdigest()[:24]
    cache_key = (
        f"govinsights:dashboard:{user.tenant_id}:{module or 'executive'}:"
        f"v{projection_version}:{filter_hash}"
    )
    try:
        cached = await request.app.state.redis.get(cache_key)
        if cached:
            return DashboardResponse.model_validate_json(cached).model_dump(mode="python")
    except Exception:
        # Redis is an optimization here. The database remains the source of truth.
        pass
    result = await dashboard(session, user.tenant_id, filters, settings, module)
    if module in (None, "notifications"):
        dead_letter_count = 0
        try:
            entries = await request.app.state.redis.xrevrange(
                settings.dead_letter_stream_name, count=400
            )
            for _, fields in entries:
                try:
                    event = EventEnvelope.model_validate_json(fields.get("event", ""))
                except Exception:
                    continue
                dead_letter_count += int(event.tenant_id == user.tenant_id)
        except Exception:
            pass
        result["operational_metrics"]["dead_letter_events"] = dead_letter_count
    serialized = DashboardResponse.model_validate(result).model_dump_json()
    try:
        await request.app.state.redis.set(
            cache_key, serialized, ex=settings.dashboard_cache_seconds
        )
    except Exception:
        pass
    return result


@router.get("/dashboards/executive", response_model=DashboardResponse)
async def executive_dashboard(
    request: Request,
    user: Reader,
    session: Session,
    settings: SettingsDep,
    date_from: date | None = None,
    date_to: date | None = None,
    department_id: uuid.UUID | None = None,
    responsible_user_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    return await _cached_dashboard(
        request,
        session,
        user,
        filters_from_query(date_from, date_to, department_id, responsible_user_id),
        settings,
        None,
    )


@router.get("/dashboards/{module}", response_model=DashboardResponse)
async def module_dashboard(
    module: str,
    request: Request,
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
    return await _cached_dashboard(
        request,
        session,
        user,
        filters_from_query(date_from, date_to, department_id, responsible_user_id),
        settings,
        module,
    )


@router.get("/search", response_model=SearchPage)
async def unified_search(
    user: Searcher,
    session: Session,
    q: Annotated[str | None, Query(min_length=2, max_length=200)] = None,
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
async def metadata(_: Reporter) -> dict[str, list[str]]:
    return {
        "modules": sorted(MODULES),
        "report_columns": sorted(REPORT_COLUMNS),
        "report_resource_types": sorted(REPORT_RESOURCE_TYPES),
    }


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
    return await list_report_runs(session, user, limit)


@router.get("/audit", response_model=list[AuditResponse])
async def audit_events(
    user: Auditor,
    session: Session,
    action: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=100000)] = 0,
) -> list[Any]:
    statement = select(AuditEvent).where(AuditEvent.tenant_id == user.tenant_id)
    if action:
        statement = statement.where(AuditEvent.action == action)
    result = await session.scalars(
        statement.order_by(AuditEvent.created_at.desc(), AuditEvent.id).limit(limit).offset(offset)
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
async def projection_status(
    request: Request, _: Reader, session: Session, settings: SettingsDep
) -> dict[str, Any]:
    checkpoint = await session.get(ProjectionCheckpoint, settings.consumer_group)
    lag: int | None = None
    pending: int | None = None
    try:
        groups = await request.app.state.redis.xinfo_groups(settings.event_stream_name)
        group = next((item for item in groups if item.get("name") == settings.consumer_group), None)
        if group is not None:
            raw_lag = group.get("lag")
            lag = int(raw_lag) if raw_lag is not None else None
            pending = int(group.get("pending", 0))
    except Exception:
        pass
    if checkpoint is None:
        return {
            "consumer": settings.consumer_group,
            "last_stream_id": "0-0",
            "last_event_at": None,
            "last_processed_at": None,
            "last_heartbeat_at": None,
            "processed_count": 0,
            "failed_count": 0,
            "projection_version": 0,
            "stale": True,
            "lag": lag,
            "pending": pending,
        }
    from datetime import timedelta

    stale = checkpoint.last_heartbeat_at is None or checkpoint.last_heartbeat_at < datetime.now(
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
                "last_heartbeat_at",
                "processed_count",
                "failed_count",
                "projection_version",
            )
        },
        "stale": stale,
        "lag": lag,
        "pending": pending,
    }


@router.post("/projections/rebuild")
async def request_rebuild(
    request: Request,
    user: Admin,
    session: Session,
    settings: SettingsDep,
    source: Literal["platform", "contracts", "documents", "notifications"],
) -> dict[str, Any]:
    if settings.internal_service_token is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Internal service authentication is not configured.",
        )
    source_urls = {
        "platform": settings.platform_api_url,
        "contracts": settings.contracts_api_url,
        "documents": settings.documents_api_url,
        "notifications": settings.notifications_api_url,
    }
    headers = {"X-Service-Token": settings.internal_service_token.get_secret_value()}
    try:
        response = await request.app.state.http_client.get(
            f"{source_urls[source].rstrip('/')}/internal/insights/snapshot/{user.tenant_id}",
            headers=headers,
        )
        response.raise_for_status()
        raw_snapshot = response.content
        snapshot = ProjectionSnapshot.model_validate_json(raw_snapshot)
    except (httpx.HTTPError, ValidationError) as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            f"The {source} snapshot is unavailable.",
        ) from exc
    if snapshot.source != source or any(
        record.tenant_id != user.tenant_id for record in snapshot.records
    ):
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "The source returned an invalid tenant snapshot.",
        )
    checksum = hashlib.sha256(raw_snapshot).hexdigest()
    try:
        imported = await import_snapshot(
            snapshot,
            checksum,
            rebuild=True,
            batch_size=200,
            state_key=f"{source}:{user.tenant_id}",
        )
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    session.add(
        AuditEvent(
            tenant_id=user.tenant_id,
            actor_user_id=user.id,
            action="projection.rebuild_requested",
            entity_type="snapshot",
            request_id=current_request_id(),
            payload={"source": source, "records": snapshot.count, "imported": imported},
        )
    )
    await session.commit()
    return {
        "status": "completed",
        "source": source,
        "records": snapshot.count,
        "imported": imported,
    }


async def _tenant_dead_letter(
    request: Request, user: UserContext, entry_id: str
) -> tuple[dict[str, str], EventEnvelope] | None:
    entries = await request.app.state.redis.xrange(
        get_settings().dead_letter_stream_name, min=entry_id, max=entry_id, count=1
    )
    if not entries:
        return None
    _, fields = entries[0]
    try:
        event = EventEnvelope.model_validate_json(fields.get("event", ""))
    except Exception:
        return None
    if event.tenant_id != user.tenant_id:
        return None
    return fields, event


@router.get("/admin/dead-letter", response_model=list[DeadLetterResponse])
async def dead_letter_entries(
    request: Request,
    user: Admin,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[dict[str, Any]]:
    entries = await request.app.state.redis.xrevrange(
        get_settings().dead_letter_stream_name, count=min(limit * 4, 400)
    )
    results: list[dict[str, Any]] = []
    for entry_id, fields in entries:
        try:
            event = EventEnvelope.model_validate_json(fields.get("event", ""))
        except Exception:
            continue
        if event.tenant_id != user.tenant_id:
            continue
        results.append(
            {
                "id": entry_id,
                "source_stream_id": fields.get("stream_id", "unknown"),
                "error": fields.get("error", "unknown")[:200],
                "event_id": event.id,
                "event_type": event.type,
                "occurred_at": event.occurred_at,
            }
        )
        if len(results) == limit:
            break
    return results


@router.post("/admin/dead-letter/{entry_id}/retry", status_code=status.HTTP_202_ACCEPTED)
async def retry_dead_letter(
    entry_id: str, request: Request, user: Admin, session: Session, settings: SettingsDep
) -> dict[str, str]:
    if len(entry_id) > 64 or not all(part.isdigit() for part in entry_id.split("-")):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dead-letter event not found.")
    resolved = await _tenant_dead_letter(request, user, entry_id)
    if resolved is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dead-letter event not found.")
    fields, event = resolved
    await request.app.state.redis.xadd(
        settings.event_stream_name,
        {"event": json.dumps(event.model_dump(mode="json"), separators=(",", ":"))},
    )
    await request.app.state.redis.xdel(settings.dead_letter_stream_name, entry_id)
    session.add(
        AuditEvent(
            tenant_id=user.tenant_id,
            actor_user_id=user.id,
            action="projection.event_retried",
            entity_type="event",
            entity_id=event.id,
            request_id=current_request_id(),
            payload={
                "dead_letter_id": entry_id,
                "source_stream_id": fields.get("stream_id", "unknown"),
                "event_type": event.type,
            },
        )
    )
    await session.commit()
    return {"status": "accepted", "event_id": str(event.id)}
