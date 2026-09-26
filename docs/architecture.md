# GovControl architecture

GovControl is developed as a distributed modular platform. The browser presents one portal,
while business capabilities may be deployed and scaled as independent applications.

```text
Next.js portal :3000
   `-- Gateway/BFF :8080 -- server-side Redis session
          |-- Platform/GovLegal API :8000 (identity and RBAC authority)
          |-- GovContracts API      :8010 (independent domain service)
          |-- GovDocuments API      :8020 (metadata, versions, links and S3)
          `-- GovNotifications API  :8030 (inbox, preferences and delivery)

GovLegal/Contracts/Documents outbox workers --> Redis Stream --> GovNotifications worker
GovNotifications scheduler --> due schedules, delivery retry and retention

PostgreSQL :5432     Redis :6379     S3-compatible storage :9000
```

## Service boundaries

- `apps/gateway` owns authentication protocol handling, server-side sessions, CSRF, explicit route
  policy, security headers and upstream resilience. It owns no business tables.
- `apps/api` owns tenants, users, OIDC subject mapping, RBAC and GovLegal. Existing API contracts
  remain compatible.
- `apps/contracts-api` owns all GovContracts data and migrations. It must not import Python code
  from `apps/api` or query platform/GovLegal tables.
- `apps/documents-api` owns document metadata, versions, resource links, lifecycle, audit, outbox
  and object storage. It validates business resources only through authenticated internal HTTP.
- `apps/notifications-api` owns notifications, recipients, preferences, versioned templates,
  schedules, delivery attempts, processed-event deduplication, audit and notification outbox. It
  never reads another service's schema.
- `apps/web` is the shared portal. It communicates only with the gateway and never stores an access
  token or refresh token.
- Redis is the local message/job infrastructure. SeaweedFS provides the local S3-compatible object
  store; the application-facing contract remains standard S3 so another provider can replace it.
- GovDocuments always uses S3-compatible storage and keeps bytes outside application containers.
  Its local Compose provider is SeaweedFS; production may replace it through configuration.

The services currently share one PostgreSQL server to keep local operation simple, but use
separate schema ownership and separate Alembic version chains. A schema can later be moved to a
dedicated PostgreSQL instance by changing only that service's connection string.

## Identity and authorization

In local mode the gateway exchanges its server-only development credential for a Platform user
context. In OIDC mode it performs Authorization Code + PKCE, verifies discovery issuer, JWKS
signature, audience, expiry, state and nonce, then asks Platform to map issuer + subject to an
active user. Platform remains the only tenant/RBAC authority.

The gateway keeps an opaque signed session handle in an HttpOnly cookie and the session record in
Redis. It issues a short-lived signed assertion containing only user and tenant identifiers for
each upstream request. Platform verifies the signature and reloads the active user, tenant, roles
and permissions from its database; any browser-supplied identity headers are discarded.

When `INTERNAL_SERVICE_TOKEN` is configured, service calls use hidden `/api/v1/internal/*`
contracts protected by a constant-time credential check. GovContracts forwards the end-user
credential only to the internal identity resolver, while Platform sends its already established
tenant context to the internal contract resolver. Production refuses to start without an internal
service credential. Rotate this credential independently from user authentication; a future
deployment may replace it with mTLS or workload identity without changing the domain APIs.
Organizational references stored by GovContracts remain opaque UUIDs. Create and update requests
validate responsible users and departments through the internal Platform directory contract, so
GovContracts neither queries identity tables nor accepts a reference belonging to another tenant.

Every HTTP request receives a UUID correlation identifier. Services preserve a valid incoming
`X-Request-ID`, propagate it across internal HTTP calls, return it to the caller and emit a JSON
access log containing service, route, status and duration. Critical audit records persist the same
identifier so an operator can correlate browser, service and audit activity.

## Events and consistency

Every critical GovLegal, GovContracts or GovDocuments mutation writes business state, local audit and a
versioned outbox event in one PostgreSQL transaction. Each service's worker delivers events to
the `govcontrol.events` Redis Stream and marks them published only after Redis accepts them. This
provides at-least-once delivery; consumers must use the event UUID for idempotency. Cross-service
workflows use events and compensating actions rather than distributed database transactions.
GovNotifications consumes the stream with a consumer group, acknowledges only completed or
dead-lettered messages, recovers idle pending messages and records the event UUID before ack. Its
controlled template map copies identifiers and action codes, not producer-supplied business text.

## Gateway routing and trust

Public routes are namespaced as `/api/v1/platform/*`, `/api/v1/govcontracts/*` and the explicit
`/api/v1/documents/*` and `/api/v1/notifications/*` capabilities. A static map
restricts both first path segment and HTTP methods. The gateway never accepts an upstream URL,
removes hop-by-hop and browser identity headers, applies request-size/rate controls and forwards a
small header allowlist. Its pooled HTTP client propagates only a fresh identity assertion and UUID
request ID. Default Compose publishes no business-service host ports; a localhost-only debug
override is maintained separately.

## Target application map

The current extraction contains Gateway/BFF, Platform/GovLegal, GovContracts, GovDocuments,
GovNotifications and their workers/schedulers.
Future bounded applications remain explicit architecture targets rather than empty services:
reporting/search and additional Gov modules. Identity remains a
Platform-owned boundary while the gateway owns protocols and sessions.

## Kubernetes readiness without Kubernetes manifests

The current target is Docker Compose only. Each service nevertheless follows portable runtime
constraints: environment-only configuration, stateless API processes, externally persisted data,
process health and dependency readiness endpoints, fixed container ports and graceful ASGI
shutdown. No Kubernetes or Helm files are maintained until an actual deployment requires them.
