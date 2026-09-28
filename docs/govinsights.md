# GovInsights

GovInsights is the independent read, search and reporting boundary for GovControl. It owns the
PostgreSQL `insights` schema, its Alembic history, a FastAPI process on internal port `8040`, and a
worker. It never reads another service's tables. Browser requests reach it only through the
Gateway allowlist at `/api/v1/insights/*`.

## Architecture and data flow

```text
Platform/GovLegal ─┐
GovContracts ──────┼─ transactional outbox → Redis Stream → GovInsights worker
GovDocuments ──────┤                                      │
GovNotifications ──┘                                      ▼
                                              tenant-scoped projections
                                                         │
                         Gateway → dashboards/search/reports → export job
                                                                  │
                                                                  ▼
                                                        object storage
```

Source writes and their outbox records commit together. Publishers use at-least-once delivery.
The worker validates a controlled event envelope, deduplicates by event UUID, rejects older source
versions, writes the projection and checkpoint atomically, and acknowledges the stream message.
Unknown event types are recorded as processed but do not create a projection. Invalid messages go
to `govcontrol.insights.dlq`; abandoned pending messages are claimed and retried with exponential
backoff before DLQ.

The principal tables are:

- `projection_resources`: normalized legal, contract, document, notification, user and department
  metadata, uniquely keyed by tenant/module/type/source ID;
- `processed_events`: the idempotency ledger;
- `projection_checkpoints`: stream position, heartbeat, counts and projection version;
- `backfill_states`: resumable snapshot import state and checksum;
- `saved_reports`, `report_runs`, `export_artifacts`: controlled report definitions and execution;
- `audit_events`, `outbox_events`: local accountability and GovInsights domain events.

No document body, authentication token, unrestricted payload, arbitrary SQL or source database
credential is copied into the read model. Search indexes only controlled identifiers and labels.

## Event contract

Messages are stored in the shared Redis Stream under the `event` field as JSON:

```json
{
  "id": "UUID",
  "type": "contracts.contract.updated.v1",
  "tenant_id": "UUID",
  "aggregate_type": "Contract",
  "aggregate_id": "UUID",
  "occurred_at": "2026-09-28T10:00:00Z",
  "payload": {
    "identifier": "CTR-2026-001",
    "display_label": "Servicii digitale",
    "status": "ACTIVE",
    "version": 4,
    "due_at": "2027-03-31T00:00:00Z",
    "amount": "125000.00",
    "currency": "RON"
  }
}
```

The allowlisted projection fields are identifier, label, status, organizational assignment,
controlled dates, amount/currency, version, deletion marker and a small type-specific attribute
allowlist. Event UUID is the delivery idempotency key. `payload.version` orders updates for a source
resource; for equal versions the newer `occurred_at` wins. Currency must be a three-letter code.

GovInsights publishes its own transactional outbox events:

- `insights.report_created.v1`, `insights.report_updated.v1`;
- `insights.report_completed.v1`, `insights.report_failed.v1`;
- `insights.export_ready.v1`;
- `insights.projection_rebuilt.v1`.

## HTTP contract

All routes below are browser-accessible only as `http://localhost:8080/api/v1/insights/...` and
require a Gateway session. Mutations also require `X-CSRF-Token`.

| Route | Permission | Purpose |
| --- | --- | --- |
| `GET /dashboards/executive` | `insights.read` | institution-wide aggregate |
| `GET /dashboards/{module}` | `insights.read` | legal/contracts/documents/notifications/platform |
| `GET /search` | `insights.search` | ranked, filtered, paginated controlled metadata search |
| `GET /metadata` | `insights.report` | report dimensions, types and columns |
| `GET,POST /reports` | `insights.report` | visible definitions/create definition |
| `PUT,DELETE /reports/{id}` | `insights.report` | owner-only mutation |
| `POST /reports/{id}/runs` | `insights.report` | queue run; export additionally needs `insights.export` |
| `GET /runs` | `insights.report` | authorized run history |
| `GET /exports` | `insights.export` | owner/admin export history |
| `GET /exports/{id}/download` | `insights.export` | authorized, non-expired download |
| `GET /audit` | `insights.audit` | tenant-scoped local audit |
| `GET /projections/status` | `insights.read` | checkpoint, heartbeat, lag and pending count |
| `POST /projections/rebuild?source=...` | `insights.admin` | controlled tenant rebuild |
| `GET /admin/dead-letter` | `insights.admin` | safe DLQ metadata, never raw payload |
| `POST /admin/dead-letter/{id}/retry` | `insights.admin` | tenant-scoped retry |

Dashboard filters are `date_from`, `date_to`, `department_id` and `responsible_user_id`. Search
also supports `q`, `module`, `resource_type`, `status`, period, responsible, `limit` and `offset`.
The source URL is generated from known resource types. Dashboard responses expose projection
version, last update and stale state. A 15-second Redis cache is keyed by tenant, module, filters
and projection version; Redis failure falls back to PostgreSQL.

Report filters, selected columns and sort keys are validated against server allowlists. A worker
transitions runs through `QUEUED → RUNNING → SUCCEEDED|FAILED`, generates CSV or XLSX, neutralizes
spreadsheet formulas, enforces row/byte/time limits and stores the result under a server-generated
key. Limit failures expose only stable codes (`ROW_LIMIT_EXCEEDED`, `SIZE_LIMIT_EXCEEDED`,
`TIME_LIMIT_EXCEEDED`).

## Identity and security boundaries

Platform remains the authority for tenant, user, roles and permissions. The Gateway resolves its
HttpOnly server-side session, strips browser identity headers, creates a signed short-lived identity
assertion and propagates the request ID. GovInsights accepts only that assertion. Direct internal
snapshot endpoints require the separate service token and are not registered in Gateway.

Every query includes the asserted tenant. Saved reports are visible to their owner, explicitly
shared roles, or an Insights administrator. Only owner/admin export artifacts can be downloaded;
foreign and cross-tenant IDs return 404. Gateway applies separate Insights timeouts, request-size
limits and rate limits for dashboard, search and export paths. Its allowlist rejects unregistered
and internal paths. The old public Platform search and legal analytics routes are blocked after the
GovInsights E2E migration; legacy implementation remains in source for rollback.

## Backfill and rebuild

For a full offline backfill:

```bash
make insights-export-snapshots
make insights-backfill
```

Each owning service creates a controlled JSON snapshot using tenant-filtered source queries. The
import validates schema/source/count, records a SHA-256 checksum, commits in batches, resumes from
its cursor and reconciles the final resource count. Repeating the same normal import is a no-op.

`make insights-rebuild` deliberately replaces the scopes present in snapshots. The admin HTTP
rebuild obtains one tenant's snapshot over authenticated internal HTTP and deletes/recreates only
that tenant/source module scope. It is audited and emits `insights.projection_rebuilt.v1`.

Rollback procedure:

1. stop `insights-worker` to freeze projection writes;
2. route portal analytics/search back to the retained legacy UI/API commit if required;
3. block `/api/v1/insights/*` at Gateway;
4. downgrade only the Insights Alembic chain, or retain its schema for investigation;
5. leave source-service data and outboxes untouched;
6. correct the consumer/snapshot, upgrade, rebuild and re-enable traffic.

Never rebuild by querying another schema directly.

## Recovery runbook

- `/health` proves process liveness. `/ready` requires PostgreSQL, Redis, Platform Identity, object
  storage, a fresh worker heartbeat and a fresh projection checkpoint.
- Inspect `/projections/status`. Growing `lag` or `pending` with a stale heartbeat means the worker
  should be restarted after dependency health is restored.
- Inspect safe DLQ metadata as an Insights administrator. Fix the incompatible producer/event
  first, then retry the selected entry. Retry removes it from DLQ only after requeueing.
- If a projection is inconsistent but events are healthy, run the tenant/source rebuild. Snapshot
  checksums and counts provide reconciliation evidence.
- Failed report/export jobs retain a safe error code. Restore object storage and retry by starting
  a new run; do not mutate an old artifact into another user's export.
- Expired artifacts are deleted from object storage and their metadata removed by the worker.
  Cleanup is idempotent.

## Retention

Exports expire after `INSIGHTS_EXPORT_RETENTION_HOURS` (24 hours locally). The worker removes both
the object and metadata. DLQ, audit, processed-event and projection retention must be set by the
institution's approved records policy before production; no destructive default is applied to
those accountability records. Source systems remain systems of record.

## Performance observations

The API reuses bounded HTTP, database, Redis and object-storage clients. Consumer/outbox batch sizes
are configurable and jobs use `FOR UPDATE SKIP LOCKED` where competing workers are safe. Projection
indexes lead with tenant/module/status, tenant/due date, tenant/department and tenant/responsible;
the controlled text expression has a PostgreSQL trigram GIN index.

On the local seeded dataset, `EXPLAIN (ANALYZE, BUFFERS)` selected
`ix_projection_tenant_module_status` for a tenant/module status aggregation (about 0.2 ms). The
trigram expression is usable for substring search; PostgreSQL reasonably preferred the small
tenant B-tree scan at only ~200 projected rows. A real Redis/PostgreSQL integration burst of 50
unique events replayed once consumed 100 stream messages and produced exactly 50 projections and
50 idempotency records. These are smoke observations, not production benchmarks.

## Local operation

```bash
make stack-up              # build and run the complete stack
make insights-check        # lint, strict types, unit tests, Alembic drift
make insights-test         # normal test suite
make web-test-e2e-live     # all live browser flows with cleanup trap
make stack-up-debug        # additionally expose 8040 on loopback
```

Normal Compose exposes only Gateway `:8080` and portal `:3000`; the debug override exposes the
service at `127.0.0.1:8040`. No Kubernetes or Helm artifacts are maintained.

## Production work intentionally outside this delivery

Use managed PostgreSQL/Redis/object storage, TLS, a real institutional OIDC registration, secret
management and tested backups. Establish retention/legal-hold rules, alert thresholds, capacity
tests and SLOs. Large tenant rebuilds currently execute synchronously behind the Gateway timeout;
production scale should use a dedicated orchestrated rebuild job and paginated snapshot transport.
Local smoke timings must not be treated as sizing evidence.
