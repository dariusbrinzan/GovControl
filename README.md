# GovControl
GovControl – Operational Risk Platform for Public Administration

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

The process health endpoint is available at `http://127.0.0.1:8000/api/v1/health`.
The readiness endpoint at `/api/v1/ready` also verifies the PostgreSQL connection.

Run backend checks with:

```bash
make api-check
make api-test
```

## Web interface

The Next.js interface provides a GovLegal dashboard and obligations view backed by the local API.

```bash
cd apps/web
npm ci
npm run dev
```

Open `http://localhost:3000/legal`, then paste the local `DEV_AUTH_TOKEN` from `.env` into
the connection field. The token is retained only in that browser's local storage. The API permits
the local web origins by default; override them through `CORS_ALLOWED_ORIGINS` only when needed.

## Database migrations

Apply the committed Alembic migrations to the local PostgreSQL container with:

```bash
make db-migrate
```

Schema changes must be made through a new Alembic migration; do not modify the
database structure manually.

## Local development authentication

Development authentication is deliberately restricted to `APP_ENV=development`.
Set a long local `DEV_AUTH_TOKEN` in `.env`, then create the local demo tenant and
administrator once:

```bash
make db-seed
```

With `make api-dev` running, inspect the backend-established tenant context:

```bash
curl -H "Authorization: Bearer $DEV_AUTH_TOKEN" http://127.0.0.1:8000/api/v1/auth/me
```

The endpoint derives the tenant from the authenticated user. It never accepts a
client-provided tenant identifier as authorization context.

## Initial platform endpoints

All endpoints below require the development bearer token and the `platform.manage`
permission. They only expose records in the authenticated user's tenant:

- `GET /api/v1/platform/tenant`
- `GET, POST /api/v1/platform/departments`
- `GET /api/v1/platform/roles`
- `GET, POST /api/v1/platform/users`
- `PUT /api/v1/platform/users/{user_id}/roles`

## GovLegal endpoints

Users with `legal.manage` can manage legal cases, decisions, obligations, enforcement proceedings,
penalty rules and documents. All records are filtered by the tenant established by the backend.

- `GET, POST /api/v1/legal/cases`
- `GET /api/v1/legal/decisions`; `POST /api/v1/legal/cases/{case_id}/decisions`
- `POST /api/v1/legal/cases/{case_id}/decisions`
- `GET, POST /api/v1/legal/obligations`; `PATCH /api/v1/legal/obligations/{id}/status`
- `GET, POST /api/v1/legal/enforcements`
- `GET, POST /api/v1/legal/penalties/rules`; `GET /api/v1/legal/penalties/rules/{id}/exposure`
- `GET, POST /api/v1/documents`; `GET /api/v1/documents/{id}/download`
- `GET /api/v1/notifications`; `PATCH /api/v1/notifications/{id}/read`
- `POST /api/v1/notifications/dispatch/deadline-reminders`
- `GET /api/v1/search/legal` and `GET /api/v1/audit/events`

## Containers

`docker compose up --build` starts PostgreSQL, the API and the Next.js interface. Apply migrations
with `make db-migrate` before using a newly built local environment. PostgreSQL and document content
use separate named volumes (`postgres_data` and `document_data`).
