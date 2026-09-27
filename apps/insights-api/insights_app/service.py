import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import Select, and_, case, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from insights_app.config import Settings
from insights_app.models import (
    AuditEvent,
    ExportArtifact,
    OutboxEvent,
    ProjectionCheckpoint,
    ProjectionResource,
    ReportRun,
    SavedReport,
)
from insights_app.observability import current_request_id
from insights_app.schemas import DashboardFilter, ReportCreate, UserContext


def _resource_conditions(
    tenant_id: uuid.UUID, filters: DashboardFilter, module: str | None = None
) -> list[Any]:
    conditions: list[Any] = [
        ProjectionResource.tenant_id == tenant_id,
        ProjectionResource.deleted.is_(False),
    ]
    if module:
        conditions.append(ProjectionResource.module == module)
    if filters.date_from:
        conditions.append(
            ProjectionResource.occurred_at
            >= datetime.combine(filters.date_from, datetime.min.time(), UTC)
        )
    if filters.date_to:
        conditions.append(
            ProjectionResource.occurred_at
            < datetime.combine(filters.date_to + timedelta(days=1), datetime.min.time(), UTC)
        )
    if filters.department_id:
        conditions.append(ProjectionResource.department_id == filters.department_id)
    if filters.responsible_user_id:
        conditions.append(ProjectionResource.responsible_user_id == filters.responsible_user_id)
    return conditions


async def dashboard(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    filters: DashboardFilter,
    settings: Settings,
    module: str | None = None,
) -> dict[str, Any]:
    conditions = _resource_conditions(tenant_id, filters, module)

    async def buckets(column: Any) -> list[dict[str, Any]]:
        rows = await session.execute(
            select(func.coalesce(column, "unassigned"), func.count())
            .where(*conditions)
            .group_by(column)
            .order_by(func.count().desc(), func.coalesce(column, "unassigned"))
        )
        return [{"key": str(key), "count": count} for key, count in rows.all()]

    total = await session.scalar(
        select(func.count()).select_from(ProjectionResource).where(*conditions)
    )
    today = datetime.now(UTC)

    async def due_count(after: datetime | None, before: datetime) -> int:
        due_conditions = [*conditions, ProjectionResource.due_at < before]
        if after is not None:
            due_conditions.append(ProjectionResource.due_at >= after)
        return int(
            await session.scalar(
                select(func.count()).select_from(ProjectionResource).where(*due_conditions)
            )
            or 0
        )

    exposure = await session.execute(
        select(ProjectionResource.currency, func.sum(ProjectionResource.amount))
        .where(
            *conditions,
            ProjectionResource.amount.is_not(None),
            ProjectionResource.currency.is_not(None),
        )
        .group_by(ProjectionResource.currency)
        .order_by(ProjectionResource.currency)
    )
    checkpoint = await session.get(ProjectionCheckpoint, settings.consumer_group)
    last_updated = checkpoint.last_processed_at if checkpoint else None
    stale = last_updated is None or last_updated < today - timedelta(
        seconds=settings.projection_stale_seconds
    )
    return {
        "module": module,
        "total": int(total or 0),
        "by_status": await buckets(ProjectionResource.status),
        "by_type": await buckets(ProjectionResource.resource_type),
        "workload_by_department": await buckets(ProjectionResource.department_id),
        "financial_exposure": [
            {"currency": currency, "amount": amount} for currency, amount in exposure.all()
        ],
        "overdue": await due_count(None, today),
        "due_soon_7": await due_count(today, today + timedelta(days=7)),
        "due_soon_30": await due_count(today, today + timedelta(days=30)),
        "due_soon_60": await due_count(today, today + timedelta(days=60)),
        "due_soon_90": await due_count(today, today + timedelta(days=90)),
        "projection_version": checkpoint.projection_version if checkpoint else 0,
        "last_updated_at": last_updated,
        "stale": stale,
    }


async def search_resources(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    query: str,
    module: str | None,
    resource_type: str | None,
    status: str | None,
    responsible_user_id: uuid.UUID | None,
    date_from: date | None,
    date_to: date | None,
    limit: int,
    offset: int,
) -> tuple[list[dict[str, Any]], int]:
    normalized = query.strip().lower()
    pattern = f"%{normalized}%"
    conditions = [
        ProjectionResource.tenant_id == tenant_id,
        ProjectionResource.deleted.is_(False),
        or_(
            func.lower(func.coalesce(ProjectionResource.identifier, "")).like(pattern),
            func.lower(func.coalesce(ProjectionResource.display_label, "")).like(pattern),
        ),
    ]
    if module:
        conditions.append(ProjectionResource.module == module)
    if resource_type:
        conditions.append(ProjectionResource.resource_type == resource_type)
    if status:
        conditions.append(ProjectionResource.status == status)
    if responsible_user_id:
        conditions.append(ProjectionResource.responsible_user_id == responsible_user_id)
    if date_from:
        conditions.append(
            ProjectionResource.occurred_at >= datetime.combine(date_from, datetime.min.time(), UTC)
        )
    if date_to:
        conditions.append(
            ProjectionResource.occurred_at
            < datetime.combine(date_to + timedelta(days=1), datetime.min.time(), UTC)
        )
    rank = case(
        (func.lower(ProjectionResource.identifier) == normalized, 0),
        (func.lower(ProjectionResource.identifier).like(f"{normalized}%"), 1),
        (func.lower(ProjectionResource.identifier).like(pattern), 2),
        else_=3,
    ).label("rank")
    total = int(
        await session.scalar(
            select(func.count()).select_from(ProjectionResource).where(*conditions)
        )
        or 0
    )
    result = await session.execute(
        select(ProjectionResource, rank)
        .where(*conditions)
        .order_by(rank, ProjectionResource.updated_at.desc(), ProjectionResource.source_id)
        .limit(limit)
        .offset(offset)
    )
    items = []
    for resource, item_rank in result.tuples().all():
        items.append(
            {
                "id": resource.id,
                "module": resource.module,
                "resource_type": resource.resource_type,
                "source_id": resource.source_id,
                "identifier": resource.identifier,
                "display_label": resource.display_label,
                "status": resource.status,
                "source_url": resource.source_url,
                "rank": item_rank,
                "updated_at": resource.updated_at,
            }
        )
    return items, total


def report_visible(report: SavedReport, user: UserContext, *, allow_admin: bool = True) -> bool:
    return report.tenant_id == user.tenant_id and (
        report.owner_user_id == user.id
        or bool(set(report.shared_with_roles).intersection(user.roles))
        or (allow_admin and "insights.admin" in user.permissions)
    )


def audit_and_outbox(
    session: AsyncSession,
    user: UserContext,
    action: str,
    event_type: str,
    entity_type: str,
    entity_id: uuid.UUID,
    payload: dict[str, Any] | None = None,
) -> None:
    safe_payload = payload or {}
    session.add(
        AuditEvent(
            tenant_id=user.tenant_id,
            actor_user_id=user.id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            request_id=current_request_id(),
            payload=safe_payload,
        )
    )
    session.add(
        OutboxEvent(
            tenant_id=user.tenant_id,
            event_type=event_type,
            aggregate_id=entity_id,
            payload={"actor_user_id": str(user.id), **safe_payload},
        )
    )


async def create_report(
    session: AsyncSession, user: UserContext, data: ReportCreate
) -> SavedReport:
    report = SavedReport(tenant_id=user.tenant_id, owner_user_id=user.id, **data.model_dump())
    session.add(report)
    await session.flush()
    audit_and_outbox(
        session, user, "report.created", "insights.report_created.v1", "report", report.id
    )
    await session.commit()
    await session.refresh(report)
    return report


async def list_reports(session: AsyncSession, user: UserContext) -> list[SavedReport]:
    rows = await session.scalars(
        select(SavedReport)
        .where(SavedReport.tenant_id == user.tenant_id)
        .order_by(SavedReport.updated_at.desc())
    )
    return [report for report in rows.all() if report_visible(report, user)]


async def require_report(
    session: AsyncSession, user: UserContext, report_id: uuid.UUID
) -> SavedReport:
    report = await session.get(SavedReport, report_id)
    if report is None or not report_visible(report, user):
        raise LookupError("report_not_found")
    return report


async def replace_report(
    session: AsyncSession, user: UserContext, report_id: uuid.UUID, data: ReportCreate
) -> SavedReport:
    report = await require_report(session, user, report_id)
    if report.owner_user_id != user.id and "insights.admin" not in user.permissions:
        raise PermissionError("report_owner_required")
    for key, value in data.model_dump().items():
        setattr(report, key, value)
    audit_and_outbox(
        session, user, "report.updated", "insights.report_updated.v1", "report", report.id
    )
    await session.commit()
    await session.refresh(report)
    return report


async def remove_report(session: AsyncSession, user: UserContext, report_id: uuid.UUID) -> None:
    report = await require_report(session, user, report_id)
    if report.owner_user_id != user.id and "insights.admin" not in user.permissions:
        raise PermissionError("report_owner_required")
    audit_and_outbox(
        session,
        user,
        "report.deleted",
        "insights.report_updated.v1",
        "report",
        report.id,
        {"deleted": True},
    )
    await session.delete(report)
    await session.commit()


async def queue_report_run(
    session: AsyncSession,
    user: UserContext,
    report_id: uuid.UUID,
    export_format: str | None,
    settings: Settings,
) -> tuple[ReportRun, ExportArtifact | None]:
    await require_report(session, user, report_id)
    run = ReportRun(
        tenant_id=user.tenant_id, report_id=report_id, requested_by=user.id, status="QUEUED"
    )
    session.add(run)
    await session.flush()
    artifact = None
    if export_format:
        artifact = ExportArtifact(
            tenant_id=user.tenant_id,
            owner_user_id=user.id,
            run_id=run.id,
            format=export_format,
            status="QUEUED",
            expires_at=datetime.now(UTC) + timedelta(hours=settings.export_retention_hours),
        )
        session.add(artifact)
    audit_and_outbox(
        session,
        user,
        "report.run",
        "insights.report_completed.v1",
        "report_run",
        run.id,
        {"queued": True},
    )
    await session.commit()
    await session.refresh(run)
    if artifact:
        await session.refresh(artifact)
    return run, artifact


def report_query(report: SavedReport, tenant_id: uuid.UUID) -> Select[Any]:
    conditions: list[Any] = [
        ProjectionResource.tenant_id == tenant_id,
        ProjectionResource.resource_type == report.resource_type,
        ProjectionResource.deleted.is_(False),
    ]
    mapping: dict[str, Any] = {
        "module": ProjectionResource.module,
        "status": ProjectionResource.status,
        "department_id": ProjectionResource.department_id,
        "responsible_user_id": ProjectionResource.responsible_user_id,
    }
    for key, column in mapping.items():
        if value := report.filters.get(key):
            conditions.append(column == value)
    statement = select(ProjectionResource).where(and_(*conditions))
    sort_mapping: dict[str, Any] = {
        "module": ProjectionResource.module,
        "resource_type": ProjectionResource.resource_type,
        "identifier": ProjectionResource.identifier,
        "display_label": ProjectionResource.display_label,
        "status": ProjectionResource.status,
        "department_id": ProjectionResource.department_id,
        "responsible_user_id": ProjectionResource.responsible_user_id,
        "occurred_at": ProjectionResource.occurred_at,
        "due_at": ProjectionResource.due_at,
        "amount": ProjectionResource.amount,
        "currency": ProjectionResource.currency,
    }
    for item in report.sort:
        column = sort_mapping[item["column"]]
        statement = statement.order_by(
            column.desc() if item["direction"] == "desc" else column.asc()
        )
    return statement.order_by(ProjectionResource.source_id)


async def purge_expired_exports(session: AsyncSession, now: datetime) -> list[str]:
    keys = list(
        await session.scalars(
            select(ExportArtifact.storage_key).where(
                ExportArtifact.expires_at <= now, ExportArtifact.storage_key.is_not(None)
            )
        )
    )
    await session.execute(delete(ExportArtifact).where(ExportArtifact.expires_at <= now))
    await session.commit()
    return [key for key in keys if key]
