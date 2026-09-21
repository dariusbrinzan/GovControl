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
