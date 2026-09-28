import json
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import fakeredis.aioredis
import pytest

from insights_app import api
from insights_app.api import _cached_dashboard, _tenant_dead_letter
from insights_app.config import get_settings
from insights_app.schemas import DashboardFilter, UserContext


def user(tenant_id: uuid.UUID) -> UserContext:
    return UserContext(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        email="admin@example.test",
        display_name="Admin",
        roles=["platform_admin"],
        permissions=["insights.admin"],
    )


@pytest.mark.asyncio
async def test_dead_letter_lookup_is_tenant_scoped() -> None:
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    tenant_id = uuid.uuid4()
    event = {
        "id": str(uuid.uuid4()),
        "type": "legal.case.updated.v1",
        "tenant_id": str(tenant_id),
        "aggregate_type": "LegalCase",
        "aggregate_id": str(uuid.uuid4()),
        "occurred_at": datetime.now(UTC).isoformat(),
        "payload": {"identifier": "CASE-1"},
    }
    entry_id = await redis.xadd(
        get_settings().dead_letter_stream_name,
        {"stream_id": "1-0", "error": "test", "event": json.dumps(event)},
    )
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(redis=redis)))

    assert await _tenant_dead_letter(request, user(tenant_id), entry_id) is not None
    assert await _tenant_dead_letter(request, user(uuid.uuid4()), entry_id) is None
    await redis.aclose()


@pytest.mark.asyncio
async def test_dashboard_cache_is_tenant_and_projection_version_scoped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    tenant_id = uuid.uuid4()
    context = user(tenant_id)
    checkpoint = SimpleNamespace(projection_version=7)
    session = SimpleNamespace(get=AsyncMock(return_value=checkpoint))
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(redis=redis)))
    response = {
        "module": "legal",
        "total": 1,
        "by_status": [],
        "by_type": [],
        "workload_by_department": [],
        "workload_by_responsible": [],
        "financial_exposure": [],
        "monthly_trend": [],
        "period_total": 1,
        "previous_period_total": 0,
        "period_change_percent": None,
        "overdue": 0,
        "due_soon_7": 0,
        "due_soon_30": 0,
        "due_soon_60": 0,
        "due_soon_90": 0,
        "projection_version": 7,
        "last_updated_at": datetime.now(UTC),
        "stale": False,
    }
    query = AsyncMock(return_value=response)
    monkeypatch.setattr(api, "dashboard", query)

    first = await _cached_dashboard(
        request, session, context, DashboardFilter(), get_settings(), "legal"
    )
    second = await _cached_dashboard(
        request, session, context, DashboardFilter(), get_settings(), "legal"
    )
    assert first["total"] == second["total"] == 1
    assert query.await_count == 1

    checkpoint.projection_version = 8
    await _cached_dashboard(
        request, session, context, DashboardFilter(), get_settings(), "legal"
    )
    assert query.await_count == 2
    await redis.aclose()
