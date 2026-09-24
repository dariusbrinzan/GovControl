# GovControl architecture

GovControl is developed as a distributed modular platform. The browser presents one portal,
while business capabilities may be deployed and scaled as independent applications.

```text
Next.js portal
   |-- Platform/GovLegal API  :8000  (identity authority during the migration)
   `-- GovContracts API       :8010  (independent domain service)
          |-- contracts PostgreSQL schema
          `-- transactional outbox

PostgreSQL :5432     Redis :6379     MinIO :9000
```

## Service boundaries

- `apps/api` owns tenants, users, RBAC and GovLegal. Existing API contracts remain compatible.
- `apps/contracts-api` owns all GovContracts data and migrations. It must not import Python code
  from `apps/api` or query platform/GovLegal tables.
- `apps/web` is the shared portal/BFF client. Keeping one frontend currently guarantees a common
  navigation, authentication experience and design system.
- Redis is the local message/job infrastructure. MinIO is the local S3-compatible object store.

The services currently share one PostgreSQL server to keep local operation simple, but use
separate schema ownership and separate Alembic version chains. A schema can later be moved to a
dedicated PostgreSQL instance by changing only that service's connection string.

## Identity and authorization

GovContracts delegates user authentication to `GET /api/v1/auth/me` on the platform API and uses
the returned server-established tenant and permission context. It never accepts a tenant ID from
the browser as authorization context. This HTTP boundary intentionally avoids shared identity
tables. Production SSO/OIDC can replace the development bearer-token authority without changing
GovContracts domain ownership.

## Events and consistency

Every critical GovContracts mutation writes its business state, local audit record and versioned
outbox event in one PostgreSQL transaction. A later publisher worker will deliver unpublished
events to Redis; consumers must be idempotent. Cross-service workflows use events and compensating
actions rather than distributed database transactions.

## Kubernetes readiness without Kubernetes manifests

The current target is Docker Compose only. Each service nevertheless follows portable runtime
constraints: environment-only configuration, stateless API processes, externally persisted data,
process health and dependency readiness endpoints, fixed container ports and graceful ASGI
shutdown. No Kubernetes or Helm files are maintained until an actual deployment requires them.
