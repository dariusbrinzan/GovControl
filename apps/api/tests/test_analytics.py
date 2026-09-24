import uuid
from datetime import date
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.security import AuthenticatedUser, get_current_user
from app.db.session import AsyncSession, get_db_session
from app.main import app
from app.repositories.analytics import AnalyticsQuery, AnalyticsRepository
from app.services.analytics import AnalyticsFilterError, AnalyticsService


@pytest.mark.asyncio
async def test_analytics_rejects_an_inverted_period_before_querying() -> None:
    service = AnalyticsService(cast(AsyncSession, object()))

    with pytest.raises(AnalyticsFilterError):
        await service.dashboard(
            tenant_id=uuid.uuid4(),
            today=date(2026, 9, 24),
            date_from=date(2026, 9, 24),
            date_to=date(2026, 9, 1),
        )


def test_monthly_activity_includes_zero_months_and_running_active_total() -> None:
    points = AnalyticsService._monthly_points(
        date_from=date(2026, 1, 15),
        date_to=date(2026, 3, 20),
        initial_active=4,
        created_by_month={date(2026, 1, 1): 2, date(2026, 3, 1): 1},
        terminal_by_month={date(2026, 2, 1): 3},
    )

    actual = [
        (point.month, point.created, point.completed, point.active_at_end) for point in points
    ]
    assert actual == [
        (date(2026, 1, 1), 2, 0, 6),
        (date(2026, 2, 1), 0, 3, 3),
        (date(2026, 3, 1), 1, 0, 4),
    ]


@pytest.mark.asyncio
async def test_analytics_aggregate_query_contains_tenant_filter() -> None:
    tenant_id = uuid.uuid4()
    execute_result = MagicMock()
    execute_result.one.return_value = (5, 2, 1, 3, 8)
    session = MagicMock(spec=AsyncSession)
    session.execute = AsyncMock(return_value=execute_result)
    repository = AnalyticsRepository(session)

    result = await repository.obligation_kpis(
        AnalyticsQuery(
            tenant_id=tenant_id,
            date_from=date(2026, 1, 1),
            date_to=date(2026, 12, 31),
            as_of_date=date(2026, 9, 24),
        )
    )

    statement = session.execute.await_args.args[0]
    assert tenant_id in statement.compile().params.values()
    assert result["active_obligations"] == 5
    assert result["completion_rate"] == 37.5


@pytest.mark.asyncio
async def test_analytics_endpoint_requires_report_permission() -> None:
    async def user_without_report_permission() -> AuthenticatedUser:
        return AuthenticatedUser(
            id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            department_id=None,
            email="officer@example.test",
            display_name="Consilier juridic",
            roles=frozenset({"legal_officer"}),
            permissions=frozenset({"legal.manage"}),
        )

    async def fake_session():
        yield cast(AsyncSession, object())

    app.dependency_overrides[get_current_user] = user_without_report_permission
    app.dependency_overrides[get_db_session] = fake_session
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/legal/analytics/dashboard")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json()["detail"] == "You do not have permission to perform this action."
