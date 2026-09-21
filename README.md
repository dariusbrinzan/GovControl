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
