# Local deployment

GovControl runs locally as independently buildable containers coordinated by Docker Compose. This
is the supported deployment simulation until an actual Kubernetes environment is justified.

## First start

1. Copy `.env.example` to `.env`.
2. Replace every `replace-with-*` value with a distinct local secret. Never commit `.env`.
3. Start the complete stack with `make stack-up`.
4. The one-shot `api-migrate`, `contracts-migrate` and `documents-migrate` containers apply their
   independent Alembic histories before APIs and workers start.
5. Seed the platform with `make db-seed`, then seed contracts with `make contracts-seed`.
6. Verify dependencies and processes with `make stack-check` and `make stack-status`.

Default addresses are:

- portal: `http://127.0.0.1:3000`;
- gateway/BFF: `http://127.0.0.1:8080`;
- object storage S3 endpoint: `http://127.0.0.1:9000`.

Platform and GovContracts are intentionally reachable only inside the Compose network. Run
`make stack-up-debug` when localhost access to ports `8000`, `8010` and `8020` is needed for
debugging.
Override `WEB_PORT` and `GATEWAY_PORT` when occupied. When either changes, also set
`NEXT_PUBLIC_GATEWAY_URL`, `PUBLIC_BASE_URL`, `PORTAL_ORIGINS` and `PORTAL_AFTER_LOGIN_URL` before
rebuilding the portal image.

## Operations

- `make stack-logs` follows application and worker logs.
- `make stack-down` removes all Compose containers and the network but preserves named database,
  Redis and object-storage volumes.
- `make platform-up` starts only PostgreSQL, Redis and object storage for host-based development.
- `make db-down` stops PostgreSQL only.

Gateway `/health` proves that the process is alive. `/ready` verifies Redis, Platform,
GovContracts and GovDocuments. GovDocuments `/ready` separately verifies PostgreSQL, S3, Redis,
Platform and GovContracts. Compose waits for readiness and successful migrations before starting
dependents.

Useful independent commands are `make documents-check`, `make documents-migrate` and
`make documents-worker`. Operational contracts, retention, recovery and backfill/rollback are in
[`govdocuments.md`](govdocuments.md).

## Authentication and secrets

`DEV_AUTH_TOKEN` is accepted only in development and is consumed by the gateway, never the browser.
The browser receives a signed opaque cookie whose server-side record is stored in Redis database 1.
State-changing requests require the CSRF value returned by `/auth/session`. Session rotation
changes both the opaque handle and CSRF value; logout deletes the Redis record.

Production configuration rejects local authentication, insecure cookies, HTTP issuer/public URLs,
missing trusted issuers, short secrets and known placeholders. Use the OIDC and rotation guides for
an institutional deployment. Authentication events are appended to `govcontrol.auth.audit` in
Redis without recording cookies, OIDC tokens or raw session identifiers.
