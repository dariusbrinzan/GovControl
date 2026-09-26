# Access-layer baseline audit

Reviewed on 2026-09-25 before introducing the GovControl gateway.

## Authoritative baseline

- Git branch: `main`; existing local documentation, Compose, Makefile, environment template and CI
  changes are intentionally preserved.
- Platform/GovLegal is a FastAPI application on port `8000`; GovContracts is an independently
  built FastAPI application on port `8010`; the Next.js portal is on port `3000`.
- The browser currently calls both APIs directly, supplies a bearer token from browser storage and
  therefore requires two public API URLs and CORS configuration on both services.
- Platform establishes tenant, roles and permissions from its own database. GovContracts delegates
  bearer-token resolution to Platform over an authenticated internal HTTP endpoint.
- Redis currently carries GovContracts outbox events. It is persistent in Compose and can also own
  short-lived gateway session, pre-authentication and rate-limit state without becoming a business
  database.
- Service-to-service calls use a separate `X-Service-Token`; correlation UUIDs are propagated and
  emitted as structured logs.
- Platform and GovContracts own separate schemas and migration histories. The gateway must not
  connect to PostgreSQL or own business records.

## Baseline verification

- Platform: Ruff and strict mypy passed; 24 pytest tests passed.
- GovContracts: Ruff and strict mypy passed; 8 pytest tests passed.
- Portal: ESLint and strict TypeScript passed; 4 Vitest tests passed; the optimized Next.js build
  produced 20 application routes.
- The existing Compose stack reported healthy Platform, GovContracts, portal, PostgreSQL, Redis and
  object-storage containers; both one-shot migration containers exited successfully.

## Gaps addressed by this phase

1. No single public API origin or explicit gateway route allowlist exists.
2. The development bearer credential is entered into and retained by the browser.
3. There is no server-side user session, CSRF control or centralized rate limiting.
4. There is no OIDC Authorization Code + PKCE implementation.
5. Upstream services do not yet accept a short-lived identity assertion issued by a trusted gateway.
6. Login/logout activity has no dedicated authentication audit stream.
7. CORS, security headers, upstream failure handling and payload limits are not centralized.

## Invariants

- Gateway routes are explicit; callers cannot choose an upstream host or arbitrary target path.
- Tenant, user, roles and permissions are never accepted from browser-controlled headers.
- Only Platform maps an OIDC identity to a GovControl user and tenant.
- Gateway sessions and OIDC tokens are server-side; the browser receives only an opaque signed
  session cookie and a non-secret CSRF token.
- GovLegal and GovContracts business behavior and data ownership remain unchanged.
- No Kubernetes or Helm resources are introduced in this phase.
