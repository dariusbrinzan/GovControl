import fakeredis.aioredis
import httpx
import pytest

from gateway_app.config import get_settings
from gateway_app.main import create_application
from gateway_app.models import OIDCIdentity
from gateway_app.oidc import OIDCClient

USER = {
    "id": "00000000-0000-0000-0000-000000000001",
    "tenant_id": "00000000-0000-0000-0000-000000000002",
    "department_id": None,
    "email": "admin@govcontrol.local",
    "display_name": "Admin",
    "roles": ["platform_admin"],
    "permissions": ["legal.manage", "contracts.manage"],
}


@pytest.mark.asyncio
async def test_local_login_proxy_csrf_request_id_and_logout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEV_AUTH_TOKEN", "server-only-development-token")
    monkeypatch.setenv("RATE_LIMIT_REQUESTS", "100")
    get_settings.cache_clear()
    observed_headers: list[httpx.Headers] = []

    async def upstream(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/internal/auth/context"):
            assert request.headers["authorization"] == "Bearer server-only-development-token"
            return httpx.Response(200, json=USER)
        observed_headers.append(request.headers)
        return httpx.Response(200, json={"ok": True})

    app = create_application()
    async with app.router.lifespan_context(app):
        await app.state.http_client.aclose()
        app.state.redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
        app.state.http_client = httpx.AsyncClient(transport=httpx.MockTransport(upstream))
        app.state.oidc_client = OIDCClient(
            app.state.http_client, app.state.redis, get_settings()
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://gateway.test"
        ) as client:
            login = await client.post("/auth/local/login")
            assert login.status_code == 200
            csrf = login.json()["csrf_token"]
            assert "httponly" in login.headers["set-cookie"].lower()
            foreign_origin = await client.post(
                "/auth/local/login", headers={"Origin": "https://attacker.example"}
            )
            assert foreign_origin.status_code == 403
            session = await client.get("/auth/session")
            assert session.status_code == 200

            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://gateway.test",
                cookies={"govcontrol_session": "forged.cookie"},
            ) as forged_client:
                assert (await forged_client.get("/auth/session")).status_code == 401

            get_response = await client.get(
                "/api/v1/platform/legal/cases",
                headers={
                    "X-Request-ID": "11111111-1111-1111-1111-111111111111",
                    "X-Tenant-ID": "attacker-tenant",
                },
            )
            assert get_response.status_code == 200
            assert observed_headers[-1]["x-request-id"] == "11111111-1111-1111-1111-111111111111"
            assert "x-tenant-id" not in observed_headers[-1]
            assert observed_headers[-1]["authorization"].startswith("Bearer eyJ")

            rejected = await client.patch(
                "/api/v1/govcontracts/contracts/00000000-0000-0000-0000-000000000003",
                json={"status": "ACTIVE"},
            )
            assert rejected.status_code == 403
            accepted = await client.patch(
                "/api/v1/govcontracts/contracts/00000000-0000-0000-0000-000000000003",
                headers={"X-CSRF-Token": csrf},
                json={"status": "ACTIVE"},
            )
            assert accepted.status_code == 200

            unknown = await client.get("/api/v1/platform/not-a-real-route")
            assert unknown.status_code == 404
            bad_logout = await client.post("/auth/logout", headers={"X-CSRF-Token": "bad"})
            assert bad_logout.status_code == 403
            logout = await client.post("/auth/logout", headers={"X-CSRF-Token": csrf})
            assert logout.status_code == 204
            assert (await client.get("/auth/session")).status_code == 401
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_authenticated_proxy_reports_upstream_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEV_AUTH_TOKEN", "server-only-development-token")
    get_settings.cache_clear()

    async def upstream(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/internal/auth/context"):
            return httpx.Response(200, json=USER)
        raise httpx.ConnectError("unavailable", request=request)

    app = create_application()
    async with app.router.lifespan_context(app):
        await app.state.http_client.aclose()
        app.state.redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
        app.state.http_client = httpx.AsyncClient(transport=httpx.MockTransport(upstream))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://gateway.test"
        ) as client:
            assert (await client.post("/auth/local/login")).status_code == 200
            response = await client.get("/api/v1/platform/legal/cases")
            assert response.status_code == 503
            assert response.json() == {
                "detail": "The requested GovControl service is unavailable."
            }
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_rate_limit_and_upstream_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RATE_LIMIT_REQUESTS", "2")
    get_settings.cache_clear()
    app = create_application()
    async with app.router.lifespan_context(app):
        await app.state.http_client.aclose()
        app.state.redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
        app.state.http_client = httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(503, json={"detail": "unavailable"})
            )
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://gateway.test"
        ) as client:
            assert (await client.get("/auth/config")).status_code == 200
            assert (await client.get("/auth/config")).status_code == 200
            limited = await client.get("/auth/config")
            assert limited.status_code == 429
            assert limited.headers["Retry-After"] == "60"
            assert limited.headers["X-Content-Type-Options"] == "nosniff"
            assert limited.headers["X-Request-ID"]
            assert (await client.get("/health")).status_code == 200
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_oidc_callback_creates_server_side_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTH_MODE", "oidc")
    monkeypatch.setenv("OIDC_ISSUER", "https://identity.example.test")
    monkeypatch.setenv("OIDC_CLIENT_ID", "govcontrol")
    get_settings.cache_clear()

    class FakeOIDCClient:
        async def begin(self) -> str:
            return "https://identity.example.test/authorize"

        async def complete(self, *, state: str, code: str) -> OIDCIdentity:
            assert state == "valid-state"
            assert code == "valid-code"
            return OIDCIdentity(
                issuer="https://identity.example.test",
                subject="institution-user",
                email="admin@example.com",
                email_verified=True,
                display_name="Admin",
            )

    async def upstream(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/internal/auth/oidc-context")
        return httpx.Response(200, json=USER)

    app = create_application()
    async with app.router.lifespan_context(app):
        await app.state.http_client.aclose()
        app.state.redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
        app.state.http_client = httpx.AsyncClient(transport=httpx.MockTransport(upstream))
        app.state.oidc_client = FakeOIDCClient()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://gateway.test"
        ) as client:
            login = await client.get("/auth/login", follow_redirects=False)
            assert login.status_code == 302
            assert login.headers["location"] == "https://identity.example.test/authorize"
            callback = await client.get(
                "/auth/callback?state=valid-state&code=valid-code", follow_redirects=False
            )
            assert callback.status_code == 302
            assert "govcontrol_session=" in callback.headers["set-cookie"]
            assert (await client.get("/auth/session")).status_code == 200
    get_settings.cache_clear()
