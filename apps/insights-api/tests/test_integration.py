import asyncio
import os
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from redis.asyncio import Redis
from sqlalchemy import delete, select

from insights_app import main as insights_main
from insights_app.config import Settings, get_settings
from insights_app.database import session_factory
from insights_app.exports import cleanup_expired_exports, process_export
from insights_app.models import (
    AuditEvent,
    ExportArtifact,
    OutboxEvent,
    ProcessedEvent,
    ProjectionCheckpoint,
    ProjectionResource,
    ReportRun,
    SavedReport,
)
from insights_app.projections import apply_event
from insights_app.schemas import DashboardFilter, EventEnvelope, ReportCreate, UserContext
from insights_app.service import (
    create_report,
    dashboard,
    list_reports,
    queue_report_run,
    search_resources,
)
from insights_app.storage import LocalExportStorage
from insights_app.worker import consume_new, ensure_group, recover_pending

pytestmark = pytest.mark.skipif(
    os.getenv("GOVCONTROL_INTEGRATION") != "1",
    reason="requires migrated PostgreSQL",
)


def event(
    tenant_id: uuid.UUID,
    source_id: uuid.UUID,
    *,
    version: int,
    status: str,
    event_id: uuid.UUID | None = None,
) -> EventEnvelope:
    return EventEnvelope(
        id=event_id or uuid.uuid4(),
        type="contracts.contract.updated.v1",
        tenant_id=tenant_id,
        aggregate_type="Contract",
        aggregate_id=source_id,
        occurred_at=datetime.now(UTC),
        payload={
            "identifier": f"CTR-{source_id}",
            "status": status,
            "version": version,
            "amount": "125.50",
            "currency": "RON",
        },
    )


def user(tenant_id: uuid.UUID, *roles: str) -> UserContext:
    return UserContext(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        email="officer@example.test",
        display_name="Officer",
        roles=list(roles),
        permissions=["insights.report", "insights.export"],
    )


@pytest.mark.asyncio
async def test_projection_is_idempotent_ordered_and_tenant_scoped() -> None:
    tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()
    source_id = uuid.uuid4()
    consumer = f"integration-{uuid.uuid4()}"
    duplicate_id = uuid.uuid4()
    try:
        async with session_factory() as session:
            newest = event(tenant_a, source_id, version=2, status="ACTIVE", event_id=duplicate_id)
            assert await apply_event(session, newest, "2-0", consumer)
            assert not await apply_event(session, newest, "2-0", consumer)
            assert await apply_event(
                session,
                event(tenant_a, source_id, version=1, status="DRAFT"),
                "3-0",
                consumer,
            )
            assert await apply_event(
                session,
                event(tenant_b, source_id, version=1, status="DRAFT"),
                "4-0",
                consumer,
            )

            resources = list(
                (
                    await session.scalars(
                        select(ProjectionResource).where(
                            ProjectionResource.tenant_id.in_([tenant_a, tenant_b]),
                            ProjectionResource.source_id == source_id,
                        )
                    )
                ).all()
            )
            assert len(resources) == 2
            by_tenant = {resource.tenant_id: resource for resource in resources}
            assert by_tenant[tenant_a].status == "ACTIVE"
            assert by_tenant[tenant_a].source_version == 2
            assert by_tenant[tenant_b].status == "DRAFT"
    finally:
        async with session_factory() as session:
            await session.execute(
                delete(ProcessedEvent).where(ProcessedEvent.tenant_id.in_([tenant_a, tenant_b]))
            )
            await session.execute(
                delete(ProjectionResource).where(
                    ProjectionResource.tenant_id.in_([tenant_a, tenant_b])
                )
            )
            await session.execute(
                delete(ProjectionCheckpoint).where(ProjectionCheckpoint.consumer == consumer)
            )
            await session.commit()


@pytest.mark.asyncio
async def test_dashboard_keeps_currency_and_resource_categories_separate() -> None:
    tenant_id = uuid.uuid4()
    settings = Settings(
        insights_database_url=get_settings().insights_database_url,
        consumer_group=f"integration-{uuid.uuid4()}",
    )
    now = datetime.now(UTC)
    try:
        async with session_factory() as session:
            session.add_all(
                [
                    ProjectionResource(
                        tenant_id=tenant_id,
                        module="contracts",
                        resource_type=resource_type,
                        source_id=uuid.uuid4(),
                        status="ACTIVE",
                        occurred_at=now,
                        due_at=now + timedelta(days=5),
                        amount=amount,
                        currency=currency,
                        source_url=f"/contracts/{uuid.uuid4()}",
                        attributes={},
                        source_version=1,
                        source_event_at=now,
                    )
                    for resource_type, amount, currency in (
                        ("contract", Decimal("100.00"), "RON"),
                        ("payment", Decimal("30.00"), "RON"),
                        ("contract", Decimal("40.00"), "EUR"),
                    )
                ]
            )
            await session.commit()
            result = await dashboard(
                session, tenant_id, DashboardFilter(), settings, module="contracts"
            )
            assert {
                (item["category"], item["currency"], item["amount"])
                for item in result["financial_exposure"]
            } == {
                ("contract", "EUR", Decimal("40.00")),
                ("contract", "RON", Decimal("100.00")),
                ("payment", "RON", Decimal("30.00")),
            }
            assert result["due_soon_7"] == 3
            assert result["operational_metrics"]["expiring_contracts_7"] == 2
    finally:
        async with session_factory() as session:
            await session.execute(
                delete(ProjectionResource).where(ProjectionResource.tenant_id == tenant_id)
            )
            await session.commit()


@pytest.mark.asyncio
async def test_search_ranking_filters_pagination_and_tenant_isolation() -> None:
    tenant_id, foreign_tenant = uuid.uuid4(), uuid.uuid4()
    responsible_id = uuid.uuid4()
    now = datetime.now(UTC)
    values = [
        (tenant_id, "ALPHA", "Exact", "ACTIVE"),
        (tenant_id, "ALPHA-002", "Prefix", "ACTIVE"),
        (tenant_id, "ZZ-ALPHA", "Contains", "CLOSED"),
        (foreign_tenant, "ALPHA", "Foreign", "ACTIVE"),
    ]
    try:
        async with session_factory() as session:
            session.add_all(
                [
                    ProjectionResource(
                        tenant_id=scoped_tenant,
                        module="legal",
                        resource_type="case",
                        source_id=uuid.uuid4(),
                        identifier=identifier,
                        display_label=label,
                        status=item_status,
                        responsible_user_id=responsible_id,
                        occurred_at=now,
                        source_url=f"/legal/cases/{uuid.uuid4()}",
                        attributes={},
                        source_version=1,
                        source_event_at=now,
                    )
                    for scoped_tenant, identifier, label, item_status in values
                ]
            )
            await session.commit()
            first_page, total = await search_resources(
                session,
                tenant_id,
                "alpha",
                "legal",
                "case",
                None,
                responsible_id,
                now.date(),
                now.date(),
                2,
                0,
            )
            assert total == 3
            assert [item["rank"] for item in first_page] == [0, 1]
            assert [item["identifier"] for item in first_page] == ["ALPHA", "ALPHA-002"]
            second_page, second_total = await search_resources(
                session,
                tenant_id,
                "alpha",
                "legal",
                "case",
                None,
                responsible_id,
                now.date(),
                now.date(),
                2,
                2,
            )
            assert second_total == 3
            assert [item["identifier"] for item in second_page] == ["ZZ-ALPHA"]
            active, active_total = await search_resources(
                session,
                tenant_id,
                None,
                "legal",
                "case",
                "ACTIVE",
                None,
                None,
                None,
                10,
                0,
            )
            assert active_total == len(active) == 2
            assert all(item["display_label"] != "Foreign" for item in active)
    finally:
        async with session_factory() as session:
            await session.execute(
                delete(ProjectionResource).where(
                    ProjectionResource.tenant_id.in_([tenant_id, foreign_tenant])
                )
            )
            await session.commit()


@pytest.mark.asyncio
async def test_pending_message_exceeding_retry_limit_moves_to_dlq() -> None:
    suffix = uuid.uuid4()
    settings = Settings(
        insights_database_url=get_settings().insights_database_url,
        redis_url=get_settings().redis_url,
        event_stream_name=f"govcontrol.test.events.{suffix}",
        dead_letter_stream_name=f"govcontrol.test.dlq.{suffix}",
        consumer_group=f"integration-{suffix}",
        consumer_name="recovery-consumer",
        pending_idle_ms=1000,
        max_delivery_attempts=1,
        retry_base_seconds=0.001,
    )
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        await ensure_group(redis, settings)
        payload = event(uuid.uuid4(), uuid.uuid4(), version=1, status="ACTIVE")
        stream_id = await redis.xadd(
            settings.event_stream_name, {"event": payload.model_dump_json()}
        )
        await redis.xreadgroup(
            settings.consumer_group,
            "original-consumer",
            {settings.event_stream_name: ">"},
            count=1,
        )
        await redis.xclaim(
            settings.event_stream_name,
            settings.consumer_group,
            "retry-consumer",
            min_idle_time=0,
            message_ids=[stream_id],
        )
        await asyncio.sleep(1.05)

        assert await recover_pending(redis, settings) == 0
        assert await redis.xlen(settings.dead_letter_stream_name) == 1
        pending = await redis.xpending(settings.event_stream_name, settings.consumer_group)
        assert pending["pending"] == 0
        async with session_factory() as session:
            checkpoint = await session.get(ProjectionCheckpoint, settings.consumer_group)
            assert checkpoint is not None
            assert checkpoint.failed_count == 1
    finally:
        await redis.delete(settings.event_stream_name, settings.dead_letter_stream_name)
        await redis.aclose()
        async with session_factory() as session:
            await session.execute(
                delete(ProjectionCheckpoint).where(
                    ProjectionCheckpoint.consumer == settings.consumer_group
                )
            )
            await session.commit()


@pytest.mark.asyncio
async def test_event_burst_and_replay_remain_exactly_once_in_projection() -> None:
    suffix = uuid.uuid4()
    tenant_id = uuid.uuid4()
    settings = Settings(
        insights_database_url=get_settings().insights_database_url,
        redis_url=get_settings().redis_url,
        event_stream_name=f"govcontrol.test.events.{suffix}",
        dead_letter_stream_name=f"govcontrol.test.dlq.{suffix}",
        consumer_group=f"integration-{suffix}",
        consumer_name="burst-consumer",
        consumer_batch_size=25,
        consumer_block_ms=100,
    )
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    envelopes = [
        event(tenant_id, uuid.uuid4(), version=1, status="ACTIVE") for _ in range(50)
    ]
    try:
        await ensure_group(redis, settings)
        for envelope in [*envelopes, *envelopes]:
            await redis.xadd(
                settings.event_stream_name, {"event": envelope.model_dump_json()}
            )
        processed = sum([await consume_new(redis, settings) for _ in range(4)])
        assert processed == 100
        async with session_factory() as session:
            count = len(
                list(
                    (
                        await session.scalars(
                            select(ProjectionResource.id).where(
                                ProjectionResource.tenant_id == tenant_id
                            )
                        )
                    ).all()
                )
            )
            assert count == 50
            assert len(
                list(
                    (
                        await session.scalars(
                            select(ProcessedEvent.event_id).where(
                                ProcessedEvent.tenant_id == tenant_id
                            )
                        )
                    ).all()
                )
            ) == 50
    finally:
        await redis.delete(settings.event_stream_name, settings.dead_letter_stream_name)
        await redis.aclose()
        async with session_factory() as session:
            await session.execute(
                delete(ProcessedEvent).where(ProcessedEvent.tenant_id == tenant_id)
            )
            await session.execute(
                delete(ProjectionResource).where(ProjectionResource.tenant_id == tenant_id)
            )
            await session.execute(
                delete(ProjectionCheckpoint).where(
                    ProjectionCheckpoint.consumer == settings.consumer_group
                )
            )
            await session.commit()


@pytest.mark.asyncio
async def test_report_export_visibility_and_expiry(tmp_path: Path) -> None:
    tenant_id = uuid.uuid4()
    owner = user(tenant_id)
    unrelated = user(tenant_id)
    auditor = user(tenant_id, "auditor")
    settings = Settings(
        insights_database_url=get_settings().insights_database_url,
        export_storage_path=tmp_path,
        export_retention_hours=1,
    )
    storage = LocalExportStorage(tmp_path)
    now = datetime.now(UTC)
    try:
        async with session_factory() as session:
            session.add(
                ProjectionResource(
                    tenant_id=tenant_id,
                    module="legal",
                    resource_type="case",
                    source_id=uuid.uuid4(),
                    identifier="CASE-INTEGRATION-1",
                    status="ACTIVE",
                    occurred_at=now,
                    source_url=f"/legal/cases/{uuid.uuid4()}",
                    attributes={},
                    source_version=1,
                    source_event_at=now,
                )
            )
            await session.commit()
            report = await create_report(
                session,
                owner,
                ReportCreate(
                    name=f"Integration {uuid.uuid4()}",
                    resource_type="case",
                    filters={"module": "legal"},
                    columns=["identifier", "status"],
                    shared_with_roles=["auditor"],
                ),
            )
            report_id = report.id
            assert await list_reports(session, unrelated) == []
            assert [item.id for item in await list_reports(session, auditor)] == [report.id]

            run, artifact = await queue_report_run(session, owner, report.id, "csv", settings)
            assert artifact is not None
            await process_export(session, storage, artifact, settings)
            await session.refresh(run)
            await session.refresh(artifact)
            assert run.status == "SUCCEEDED"
            assert run.row_count == 1
            assert artifact.status == "SUCCEEDED"
            assert artifact.storage_key is not None
            assert b"CASE-INTEGRATION-1" in await storage.get(artifact.storage_key)

            artifact.expires_at = now - timedelta(seconds=1)
            await session.commit()
            assert await cleanup_expired_exports(session, storage, datetime.now(UTC)) == 1
            assert await session.get(ExportArtifact, artifact.id) is None
            with pytest.raises(FileNotFoundError):
                await storage.get(artifact.storage_key)

            session.add_all(
                [
                    ProjectionResource(
                        tenant_id=tenant_id,
                        module="legal",
                        resource_type="case",
                        source_id=uuid.uuid4(),
                        identifier=f"CASE-LARGE-{index}",
                        display_label="x" * 500,
                        status="ACTIVE",
                        occurred_at=now,
                        source_url=f"/legal/cases/{uuid.uuid4()}",
                        attributes={},
                        source_version=1,
                        source_event_at=now,
                    )
                    for index in range(3)
                ]
            )
            report.columns = ["identifier", "display_label", "status"]
            await session.commit()
            size_run, size_artifact = await queue_report_run(
                session,
                owner,
                report_id,
                "csv",
                settings.model_copy(update={"export_max_bytes": 1024}),
            )
            assert size_artifact is not None
            await process_export(
                session,
                storage,
                size_artifact,
                settings.model_copy(update={"export_max_bytes": 1024}),
            )
            await session.refresh(size_run)
            assert size_run.status == "FAILED"
            assert size_run.error_code == "SIZE_LIMIT_EXCEEDED"

            timeout_run, timeout_artifact = await queue_report_run(
                session,
                owner,
                report_id,
                "csv",
                settings.model_copy(update={"export_timeout_seconds": 0.000001}),
            )
            assert timeout_artifact is not None
            await process_export(
                session,
                storage,
                timeout_artifact,
                settings.model_copy(update={"export_timeout_seconds": 0.000001}),
            )
            await session.refresh(timeout_run)
            assert timeout_run.status == "FAILED"
            assert timeout_run.error_code == "TIME_LIMIT_EXCEEDED"
    finally:
        async with session_factory() as session:
            await session.execute(delete(OutboxEvent).where(OutboxEvent.tenant_id == tenant_id))
            await session.execute(delete(AuditEvent).where(AuditEvent.tenant_id == tenant_id))
            await session.execute(
                delete(ExportArtifact).where(ExportArtifact.tenant_id == tenant_id)
            )
            await session.execute(delete(ReportRun).where(ReportRun.tenant_id == tenant_id))
            await session.execute(delete(SavedReport).where(SavedReport.tenant_id == tenant_id))
            await session.execute(
                delete(ProjectionResource).where(ProjectionResource.tenant_id == tenant_id)
            )
            await session.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize("failed_component", ["redis", "platform_identity", "object_storage"])
async def test_readiness_reports_dependency_failure(
    failed_component: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(
        insights_database_url=get_settings().insights_database_url,
        consumer_group=f"readiness-{uuid.uuid4()}",
    )
    checkpoint = ProjectionCheckpoint(
        consumer=settings.consumer_group,
        last_stream_id="1-0",
        last_processed_at=datetime.now(UTC),
        last_heartbeat_at=datetime.now(UTC),
        processed_count=1,
        failed_count=0,
        projection_version=1,
    )
    async with session_factory() as session:
        session.add(checkpoint)
        await session.commit()

    async def dependency_call(component: str) -> None:
        if component == failed_component:
            raise RuntimeError(f"{component} unavailable")

    async def redis_ping() -> None:
        await dependency_call("redis")

    async def platform_get(*_args: object, **_kwargs: object) -> SimpleNamespace:
        await dependency_call("platform_identity")
        return SimpleNamespace(raise_for_status=lambda: None)

    async def storage_ready() -> None:
        await dependency_call("object_storage")

    redis = SimpleNamespace(ping=AsyncMock(side_effect=redis_ping))
    http_client = SimpleNamespace(get=AsyncMock(side_effect=platform_get))
    storage = SimpleNamespace(ready=AsyncMock(side_effect=storage_ready))
    monkeypatch.setattr(insights_main, "get_settings", lambda: settings)
    app = insights_main.create_application()
    app.state.redis = redis
    app.state.http_client = http_client
    app.state.export_storage = storage
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://insights.test"
        ) as client:
            ready = await client.get("/ready")
            assert ready.status_code == 503
            assert ready.json()["detail"]["components"][failed_component] == "unavailable"
    finally:
        async with session_factory() as session:
            await session.execute(
                delete(ProjectionCheckpoint).where(
                    ProjectionCheckpoint.consumer == settings.consumer_group
                )
            )
            await session.commit()
