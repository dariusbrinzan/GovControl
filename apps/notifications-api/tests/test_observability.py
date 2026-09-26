import httpx
import pytest

from notifications_app.main import create_application


@pytest.mark.asyncio
async def test_health_propagates_valid_request_id() -> None:
    app = create_application()
    request_id = "11111111-1111-4111-8111-111111111111"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://notifications.test"
    ) as client:
        response = await client.get("/health", headers={"X-Request-ID": request_id})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == request_id


@pytest.mark.asyncio
async def test_health_replaces_invalid_request_id() -> None:
    app = create_application()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://notifications.test"
    ) as client:
        response = await client.get("/health", headers={"X-Request-ID": "not-a-uuid"})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] != "not-a-uuid"
