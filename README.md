# GovControl
GovControl – Operational Risk Platform for Public Administration

The repository contains independently runnable application boundaries: the API gateway/BFF,
Platform/GovLegal, GovContracts, GovDocuments, GovNotifications and the shared Next.js portal. See
[`docs/architecture.md`](docs/architecture.md) for ownership and communication rules.
The reproducible local deployment procedure is documented in
[`docs/local-deployment.md`](docs/local-deployment.md).
The requirement-by-requirement delivery summary and verification evidence are in
[`docs/implementation-status.md`](docs/implementation-status.md).

## Local database

GovControl uses PostgreSQL 16 in Docker for local development. The database data is
kept in the Docker named volume `postgres_data`, so recreating the container does
not remove data.

```bash
cp .env.example .env
# Edit POSTGRES_PASSWORD and set the same password in DATABASE_URL.
make db-up
```

Check the database status with `make db-status`, follow logs with `make db-logs`,
and stop it with `make db-down`.

## API foundation

The backend is a Python 3.12 FastAPI application managed with `uv`. Install its
dependencies and start the development server:

```bash
cd apps/api
uv sync
cd ../..
make api-dev
```

When run directly on the host, the process health endpoint is available at
`http://127.0.0.1:8000/api/v1/health`.
The readiness endpoint at `/api/v1/ready` also verifies the PostgreSQL connection.

Run backend checks with:

```bash
make api-check
make api-test
```

## Gateway/BFF

The independent FastAPI gateway is the browser-facing access boundary. For host development run
`make gateway-dev`; its isolated quality gate is `make gateway-check`. It stores sessions and rate
counters in Redis database 1 and calls Platform/GovContracts through fixed upstream URLs. It never
connects to either business database.

## Web interface

The Next.js interface provides an institutional GovLegal workspace backed by the local API. It
includes a responsive application shell, role-aware navigation, operational lists and detail
pages, global search, notifications, audit history, reports and an analytics dashboard with
accessible charts and CSV exports.
The same portal exposes GovContracts at `/contracts`, with a contractual dashboard, status chart,
registry, CSV export, create flow and complete contract files.

```bash
cd apps/web
npm ci
npm run dev
```

Open `http://localhost:3000/legal` and select **Conectează aplicația**. The browser receives an
HttpOnly opaque session cookie from the gateway; `DEV_AUTH_TOKEN`, OIDC access tokens and refresh
tokens are never exposed to browser storage. The local token is read only by the gateway process.

Frontend quality checks:

```bash
make web-check       # ESLint, strict TypeScript, unit tests and production build
make web-test-e2e    # Chromium navigation and authentication-shell tests
make web-test-e2e-live # real local Platform + GovContracts browser flow
```

Install the Playwright browser once before the first E2E run with
`cd apps/web && npx playwright install chromium`.

## Database migrations

Apply the committed Alembic migrations to the local PostgreSQL container with:

```bash
make db-migrate
make contracts-migrate
make documents-migrate
make notifications-migrate
```

Schema changes must be made through a new Alembic migration; do not modify the
database structure manually.

## Local development authentication

Development authentication is deliberately restricted to `APP_ENV=development`.
Set a long local `DEV_AUTH_TOKEN` in `.env`. It is a server-side bootstrap credential used only
when `APP_ENV=development` and `AUTH_MODE=local`. Then create or refresh the idempotent dataset:

```bash
make db-seed
make contracts-seed
```

The development seed includes the tenant and role model plus representative departments,
users, cases, decisions, obligations across every status, status history, enforcement
proceedings, penalty rules, downloadable sample documents, notifications and audit events.
Its stable identifiers prevent duplicates when the command is run again; relative deadlines
are refreshed so dashboard examples remain useful.

With the gateway running, create a server-side session and inspect it without exposing the
development credential to the browser:

```bash
curl -c /tmp/govcontrol.cookies -X POST http://127.0.0.1:8080/auth/local/login
curl -b /tmp/govcontrol.cookies http://127.0.0.1:8080/auth/session
```

The endpoint derives the tenant from the authenticated user. It never accepts a
client-provided tenant identifier as authorization context.

## Initial platform endpoints

All endpoints below require a gateway session and the `platform.manage` permission. Public gateway
paths start with `/api/v1/platform`; upstream paths shown below remain internal contracts.

- `GET /api/v1/platform/tenant`
- `GET, POST /api/v1/platform/departments`
- `GET /api/v1/platform/roles`
- `GET, POST /api/v1/platform/users`
- `PUT /api/v1/platform/users/{user_id}/roles`
- `GET /api/v1/platform/directory` for tenant-scoped assignment labels used by business modules

## GovLegal endpoints

Users with `legal.manage` can manage legal cases, decisions, obligations, enforcement proceedings
and penalty rules. Documents are authorized with dedicated `documents.*` permissions. All records
are filtered by the tenant established by the backend.

- `GET, POST /api/v1/legal/cases`
- `GET /api/v1/legal/cases/{id}`
- `GET /api/v1/legal/decisions`; `POST /api/v1/legal/cases/{case_id}/decisions`
- `POST /api/v1/legal/cases/{case_id}/decisions`
- `GET, POST /api/v1/legal/obligations`; `PATCH /api/v1/legal/obligations/{id}/status`
- `GET /api/v1/legal/obligations/{id}`
- `GET, POST /api/v1/legal/enforcements`
- `GET, POST /api/v1/legal/penalties/rules`; `GET /api/v1/legal/penalties/rules/{id}/exposure`
- GovLegal document views call the independent `/api/v1/documents` Gateway capability.
- GovLegal publishes deadline, enforcement and penalty events; the unified notification inbox is
  served by GovNotifications through `/api/v1/notifications/*`.
- `GET /api/v1/search/legal` and `GET /api/v1/audit/events`
- `GET /api/v1/legal/analytics/dashboard` for tenant-scoped KPI and chart aggregates
- `GET /api/v1/legal/analytics/filters` for tenant-scoped reporting filter options

The analytics endpoint requires `legal.report`; the audit endpoint requires `audit.view`.
Development seed data creates platform administrator, legal director, legal officer and auditor
roles with scoped permissions.

## GovContracts endpoints

GovContracts is an independently runnable FastAPI service on internal port `8010`. It owns the `contracts`
PostgreSQL schema and its own Alembic history. `contracts.manage` authorizes operational changes;
`contracts.report` authorizes the dashboard.

- `GET, POST /api/v1/contracts`
- `GET /api/v1/contracts/page` with server-side search, status filters and pagination
- `GET /api/v1/contracts/dashboard`
- `GET /api/v1/contracts/{id}` and `GET /api/v1/contracts/{id}/overview`
- `PATCH /api/v1/contracts/{id}`
- `PATCH /api/v1/contracts/{id}/status`
- `GET, POST /api/v1/contracts/{id}/parties`
- `GET, POST /api/v1/contracts/{id}/amendments`
- `GET, POST /api/v1/contracts/{id}/milestones`
- `PATCH /api/v1/contracts/{id}/milestones/{item_id}/status`
- `GET, POST /api/v1/contracts/{id}/obligations`
- `PATCH /api/v1/contracts/{id}/obligations/{item_id}/status`
- `GET, POST /api/v1/contracts/{id}/payments`
- `PATCH /api/v1/contracts/{id}/payments/{item_id}/status`
- `GET /api/v1/contracts/audit` with tenant-scoped pagination

Contract documents continue through the shared `/api/v1/documents` capability. The document API
validates the contract over HTTP and never reads GovContracts tables. Every critical GovContracts
mutation writes a local audit event and a versioned outbox event in the same transaction.

Run the publisher locally with `make contracts-worker`. It delivers pending outbox messages to the
`govcontrol.events` Redis Stream using an at-least-once delivery model.

## GovDocuments endpoints

GovDocuments is independently runnable on internal port `8020`, owns PostgreSQL schema `documents`
and is the only service allowed to access document objects. Browser traffic always uses Gateway.

- `GET, POST /api/v1/documents` for pagination/search/filter and streaming upload;
- `GET /api/v1/documents/{id}` and `/versions`;
- `POST /api/v1/documents/{id}/versions` with `If-Match`;
- `GET /api/v1/documents/{id}/download` for streamed available content;
- `PATCH /api/v1/documents/{id}` with optimistic ETag control;
- link/unlink, archive, soft-delete, restore and audit subresources.

The upload worker supports quarantine/ClamAV scanning and publishes a transactional outbox to the
shared Redis Stream. See [`docs/govdocuments.md`](docs/govdocuments.md) for the full HTTP/event
contract, retention, recovery, migration rollback and local performance observations.

## GovNotifications

GovNotifications is independently runnable on internal port `8030`, owns PostgreSQL schema
`notifications`, and consumes controlled GovLegal, GovContracts and GovDocuments events. It owns
the unified inbox, recipients, preferences, templates, schedules, delivery attempts, deduplication,
audit and its own transactional outbox. Browser access is only through Gateway:

- `GET /api/v1/notifications` with status/category/severity/date filters and pagination;
- `GET /api/v1/notifications/unread-count`;
- `PATCH /api/v1/notifications/{id}/read|unread|archive|restore`;
- `POST /api/v1/notifications/mark-all-read`;
- `GET, PUT /api/v1/notifications/preferences`;
- authorized template, audit and delivery administration routes.

Run `make notifications-check`, `make notifications-test-integration`,
`make notifications-worker` or `make notifications-scheduler` for the isolated service. Migration,
event, delivery, retention, recovery and rollback details are in
[`docs/govnotifications.md`](docs/govnotifications.md).

## Containers

`docker compose up --build` starts PostgreSQL, Redis, S3-compatible object storage, all APIs, the
gateway and the Next.js interface. One-shot migration containers apply the four independent
Alembic chains before the corresponding APIs and workers are allowed to start.
Use `make db-migrate`, `make contracts-migrate`, `make documents-migrate` and
`make notifications-migrate` when running directly.
For infrastructure-only local development, use `make platform-up`.
The public application ports default to `8080` for the gateway and `3000` for the portal. Platform
and GovContracts have no host ports in the normal Compose topology. Use `make stack-up-debug` to
bind their debugging ports to localhost explicitly.

GovDocuments uses S3-compatible storage and stores local objects in the persistent SeaweedFS
volume. It depends only on the standard S3 interface, so the provider can later be replaced through
environment configuration. No Kubernetes or Helm manifests are required for this
local setup; the containers remain portable through environment-only configuration, independent
health/readiness probes and external state.

The portal calls only `http://127.0.0.1:8080`. Platform requests use the
`/api/v1/platform/*` prefix, GovContracts uses `/api/v1/govcontracts/*`, and GovDocuments uses the
explicit `/api/v1/documents/*` routes.
GovNotifications uses the explicit `/api/v1/notifications/*` allowlist; internal ingestion and
scheduling endpoints are not browser-routable.
The gateway uses an explicit route allowlist, pooled upstream connections, payload limits, rate
limiting, request correlation and consistent dependency errors.

The local static token is rejected outside development. Production requires `AUTH_MODE=oidc`, HTTPS,
secure cookies, trusted issuers and strong independently generated service/session secrets. See
[`docs/oidc-entra.md`](docs/oidc-entra.md), [`docs/secret-rotation.md`](docs/secret-rotation.md) and
[`docs/threat-model.md`](docs/threat-model.md). Internal calls propagate `X-Request-ID`; the same
UUID is available in structured request logs and audit records.
