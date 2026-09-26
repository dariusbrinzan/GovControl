# GovNotifications

## Boundary and data ownership

`apps/notifications-api` is a separately runnable FastAPI service and image. It owns only the
PostgreSQL `notifications` schema and its own Alembic version table. Runtime code never joins or
queries Platform, GovLegal, GovContracts or GovDocuments tables. Identity and recipient email are
resolved through authenticated Platform HTTP contracts.

Owned tables are `notifications`, `recipients`, `preferences`, `templates`, `schedules`,
`delivery_attempts`, `processed_events`, `audit_events` and `outbox_events`. Legacy Platform and
GovContracts notification tables remain unchanged and are not used by public routes.

## Event and delivery flow

```text
business mutation
  -> producer transaction + producer outbox
  -> Redis Stream govcontrol.events
  -> consumer group govnotifications-v1
  -> event UUID deduplication
  -> allowlisted event mapping + versioned controlled template
  -> notification + recipient/delivery + audit + notification outbox transaction
  -> IN_APP immediately; optional EMAIL scheduler
  -> ack Redis message
```

Messages are at-least-once. `processed_events.event_id`, the tenant-scoped notification
deduplication key and the tenant-scoped schedule key cover repeated deliveries and scheduler
restarts. Pending Redis messages are reclaimed with `XAUTOCLAIM`. Failures use exponential backoff
and are moved to `govcontrol.notifications.dlq` after the configured limit.

Subscribed contracts include contract activity/expiry, milestones, obligations and payments;
document upload/version/availability/rejection/archive/restore; legal deadlines/overdue,
enforcement and penalty exposure; and controlled administrative/security events. Payload values
are reduced to UUIDs and action codes before rendering. Arbitrary payload text is never inserted
into a notification.

## HTTP and authorization

The browser calls only Gateway `/api/v1/notifications/*`. Gateway accepts only known notification
paths and methods, discards browser identity headers, enforces the session, CSRF on mutations,
separate read/mutation rates, body size and timeout, and sends a short-lived identity assertion plus
request ID. GovNotifications validates that assertion and reloads the active identity/RBAC context
from Platform.

Permissions are `notifications.read`, `notifications.manage`, `notifications.preferences`,
`notifications.admin` and `notifications.audit`. Inbox queries always require both tenant ID and
recipient user ID. Delivery administration is tenant-scoped. Internal create/schedule routes require
the service credential and cannot be reached through the Gateway route allowlist.

## Templates and channels

Templates have a stable key and immutable incrementing versions. Only explicitly declared, simple
placeholders are accepted; attributes, indexing, conversions, formatting expressions, missing and
unknown variables are rejected. The active template is selected deterministically.

IN_APP is mandatory. EMAIL is opt-in twice: globally and by an explicit user/category preference.
The local adapter records only notification ID/category and sends nothing. Production refuses an
enabled EMAIL channel without complete SMTP configuration. SMTP secrets are represented as secret
values and never returned by APIs or logged. WEBHOOK has an interface placeholder but startup
rejects enabling it until a secure implementation exists.

## Operations, retention and recovery

- `/health` checks the process; `/ready` checks PostgreSQL, Redis, Platform Identity and enabled
  channel configuration.
- `notifications-worker` consumes/reclaims events and publishes notification outbox rows.
- `notifications-scheduler` processes due schedules, retries delivery and removes expired records.
- Default retention is 365 days and is configurable from 30 to 3650 days. A notification is removed
  only after its explicit `expires_at`; old audit rows are removed at the retention cutoff.
- Inspect the DLQ before replay. Correct the dependency/configuration, then use the authorized manual
  delivery retry API or replay the original event with its original event UUID. Idempotency prevents
  an additional notification.
- During Redis outage, producer outbox rows and consumer pending messages remain recoverable. During
  Platform outage, identity/SMTP recipient resolution fails closed and is retried.

Useful commands:

```bash
make notifications-migrate
make notifications-check
make notifications-test-integration
make notifications-worker
make notifications-scheduler
```

## Legacy migration and rollback

Export and import are explicit and repeatable:

```bash
make notifications-export-legacy
make notifications-backfill
```

The importer preserves tenant, resolved recipient, state, timestamps, title/body and resource link.
Deterministic UUIDs and `legacy:<source>:<id>` keys make repeat runs no-ops, and every import verifies
its recipient link. Source rows are never deleted.

Rollback at this stage is operational: stop notification consumers/API, route to a release that
still exposes the legacy endpoints, and keep both legacy schemas untouched. Do not downgrade the
notification migration while data is needed. Forward recovery is preferred: migrate, backfill again
and restart worker/scheduler.

## Local performance observations

The API reuses bounded HTTP and Redis clients; SQLAlchemy uses pooled connections; stream and outbox
work are bounded by configurable batches and locked with `SKIP LOCKED`. A local PostgreSQL smoke
test inserted 40 unique events and replayed all 40 in 0.79 seconds, producing exactly 40 rows. Local
tests also cover retry/DLQ. These checks validate bounded behavior and idempotency only;
they are not production throughput benchmarks. Load, SMTP provider limits, database sizing, Redis
persistence and alert thresholds must be measured in the target institution environment.
