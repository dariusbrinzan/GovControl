# GovControl implementation status

Status reviewed on 2026-09-28 against the initial project brief, GovContracts extraction,
gateway/SSO, GovDocuments, GovNotifications and GovInsights extraction goals.

## Delivered boundaries

| Boundary | Ownership | Runtime |
| --- | --- | --- |
| Platform/GovLegal | tenants, identity, RBAC, organization and GovLegal | FastAPI `:8000` |
| GovContracts | complete contractual domain, local audit and outbox | FastAPI `:8010` |
| GovContracts worker | outbox publication and due-date event generation | independent worker |
| GovDocuments | metadata, versions, links, lifecycle, audit, outbox and S3 access | FastAPI `:8020` |
| GovDocuments worker | malware scan transitions and document outbox publication | independent worker |
| GovNotifications | unified inbox, preferences, templates, schedules, delivery, audit and outbox | FastAPI `:8030` |
| GovNotifications worker/scheduler | event consumption, pending recovery, retry and retention | independent processes |
| GovInsights | dashboards, projections, search, reports, exports and audit | FastAPI `:8040` |
| GovInsights worker | event consumption, recovery, report/export jobs and retention | independent worker |
| Portal | common institutional shell and module user interfaces | Next.js `:3000` |
| Gateway/BFF | OIDC/local login, Redis sessions, CSRF, routing and edge policy | FastAPI `:8080` |
| Infrastructure | PostgreSQL, Redis Stream and S3-compatible object storage | Docker Compose |

GovContracts owns `contracts`, GovDocuments owns `documents`, GovNotifications owns
`notifications`, and GovInsights owns `insights`; each has an independent Alembic history. None
imports Platform code or queries another service's tables.
GovDocuments validates legal and contractual resource ownership through authenticated internal
HTTP contracts. Organizational references are validated by GovContracts through Platform's
internal directory contract.

## GovContracts scope

Implemented capabilities include tenant-scoped contracts, parties/suppliers, responsible users and
departments, dates, currencies and values, lifecycle transitions, amendments, milestones,
obligations, payments, associated documents, reminders, notifications, status history, audit and
versioned domain events. Dashboard values are grouped by currency rather than combined across
incompatible monetary units.

The portal includes dashboard KPIs and charts, registry search/filter/pagination/CSV export,
create/edit forms, organizational assignment controls, complete detail pages, related-record state
transitions, document upload/download, notifications and correlated audit history. Loading, empty
and error states are present in each data view.

## Platform characteristics

- Backend-enforced RBAC and server-established tenant context.
- Development bearer authentication disabled outside development; OIDC terminates at the gateway
  and issuer-qualified subject mapping remains in Platform Identity.
- Separate internal service credential, constant-time verification and hidden internal endpoints.
- UUID request correlation propagated between services, structured HTTP/worker logs and correlated
  audit records.
- Transactional outbox with at-least-once Redis Stream delivery; event UUIDs are idempotency keys.
- Liveness, dependency readiness, graceful worker shutdown and restart policies.
- One-shot, independently versioned migration containers gate API/worker startup.

## GovInsights scope

GovInsights owns normalized tenant-scoped read models for legal activity, contracts, documents,
notifications, users and departments. Its independent Redis consumer group provides event UUID
deduplication, source-version ordering, pending recovery, bounded retry, DLQ, checkpoints,
heartbeat and lag reporting. Controlled snapshots from each owning service support resumable,
idempotent backfill and tenant/source-scoped rebuild without cross-schema access.

The portal uses GovInsights for the executive and module dashboards, the GovLegal landing page,
unified search, report builder and CSV/XLSX export history. Dashboards expose monthly trend,
status/type distribution, workload, deadline windows, period comparison and financial exposure
separated by both currency and resource category. Accessible tables provide drill-down links.

Saved reports use allowlisted resource types, filters, columns and sort keys. Runs and asynchronous
exports have explicit state, generated storage keys, authorization, expiry and cleanup. Local
audit covers report lifecycle, export/download, rebuild and DLQ retry; corresponding events use a
transactional outbox. Gateway has an exact Insights route/method allowlist, dedicated limits and
timeouts, and blocks both internal snapshot contracts and migrated legacy analytics/search routes.

## GovDocuments scope

GovDocuments now owns new document writes end-to-end. It provides streaming upload/download,
incremental SHA-256, safe filename/MIME/size validation, immutable versions, search/filter/page,
multiple business links, ETag concurrency, classification, retention, archive, soft delete,
restore, tenant-scoped audit and versioned outbox events. Server-generated UUID keys isolate S3
objects. QUARANTINED/SCANNING/AVAILABLE/REJECTED states are implemented; production configuration
requires ClamAV and unavailable versions cannot be downloaded.

GovLegal case/obligation/registry views and GovContracts details use only the Gateway
`/api/v1/documents` contract. Platform's legacy public document router is removed from runtime but
legacy rows and filesystem bytes remain intact as rollback material. An idempotent verified
backfill migrated all 6 source rows and links; its second run skipped and reverified all 6.

## Verification evidence

- GitHub Actions independently enforces lint, strict type checking, tests, Alembic verification
  and Docker builds for the backend boundaries. The portal runs lint, strict types, Vitest,
  production build and mock E2E including GovInsights.
- Platform: Ruff, strict mypy and 29 pytest tests.
- Gateway: Ruff, strict mypy and 14 pytest security/integration tests.
- GovContracts: Ruff, strict mypy and 9 pytest tests.
- GovDocuments: Ruff, strict mypy and 30 pytest tests, including upload limits, spooling,
  unavailable states, S3 failures, RBAC, tenant/resource isolation and outbox shape.
- GovNotifications: Ruff, strict mypy, security/unit tests and PostgreSQL integration coverage for
  filters, pagination, status changes, tenant/user isolation, preferences, deduplication, safe
  outbox payloads, backfill and the local email sink.
- GovInsights: Ruff, strict mypy, 23 unit tests and 9 PostgreSQL/Redis integration cases. Coverage
  includes currency/category aggregation, RBAC visibility, IDOR/tenant isolation, duplicate and
  out-of-order events, a replayed 50-event burst, pending recovery/DLQ, CSV/XLSX safety, expiry,
  dependency readiness failures, controlled snapshots and dashboard cache invalidation.
- The notification backfill reconciled 5 Platform and 3 GovContracts legacy rows; the second run
  imported zero, skipped/reverified all 8, and left both source tables untouched.
- Portal: ESLint, strict TypeScript, 4 Vitest tests and optimized Next.js build including executive,
  module, search, report-builder and export-history routes.
- Alembic autogeneration checks report no missing operations for all five chains.
- Five clean temporary databases verified Platform, GovContracts, GovDocuments, GovNotifications
  and GovInsights upgrade, full reverse-order downgrade and complete upgrade again.
- Idempotent GovContracts seed verified stable contract and document counts across repeated runs.
- Real Playwright flows cover GovLegal dashboard/cases, GovContracts dashboard/registry/detail,
  a restored contract mutation, workflow controls, audit, session logout and a revoked-session
  recovery against the containerized stack.
- Three real GovDocuments Playwright flows cover legal and contract upload, exact downloaded
  content, versions, audit, CSRF rejection, browser tenant-header stripping, soft delete and restore
  after reload. Development-only cleanup removes their DB, S3 and Redis Stream artifacts.
- The real GovInsights browser flow covers login, executive/legal/contracts dashboards, ignored
  forged tenant headers, a contract event reaching unified search, saved report, asynchronous CSV
  export/download, foreign export ID rejection, logout and idempotent artifact cleanup.
- A local concurrency smoke run completed 100 Redis-session requests and 40 authenticated
  Platform proxy requests without errors; the gateway reuses one pooled HTTP client.
- A local GovNotifications burst inserted 40 events and replayed the same 40 in 0.79 seconds,
  producing exactly 40 notifications. This is an idempotency smoke observation, not a benchmark.
- A local GovInsights Redis/PostgreSQL burst consumed 50 unique projection events and their replay,
  leaving exactly 50 read models and idempotency records. Dashboard aggregation used the
  tenant/module/status index in the seeded query-plan smoke. These are not production benchmarks.
- A full controlled GovInsights rebuild imported 61 Platform, 13 GovContracts, 6 GovDocuments and
  156 GovNotifications records; an immediate repeat imported zero records from every source.
- Browser verification passes 9 mock flows and 8 serialized live flows across all implemented
  modules; cleanup removes report, export, notification, document, audit and stream artifacts.
- Container smoke tests cover readiness, authenticated internal calls, tenant-reference rejection,
  outbox delivery and document upload/download through S3.
- Four concurrent 24 MiB uploads through the real Gateway completed successfully in 3.75 seconds
  local wall time; observed RSS was about 58 MiB Gateway and 133 MiB GovDocuments. This is a smoke
  observation, not a production benchmark.
- Final backfill reconciliation reports 6 legacy rows, 6 GovDocuments rows, 6 versions, 6 links,
  6 S3 objects and zero unpublished document outbox events; all test artifacts were removed.

## Intentional future work

No Kubernetes or Helm manifests are maintained now, per the current product decision. Containers
remain portable through stateless APIs, external persistence, environment configuration, probes
and graceful shutdown. Add deployment manifests only for a concrete target environment.

GovNotifications and GovInsights are implemented boundaries. Production still needs a real institutional OIDC
registration, managed SMTP (if enabled), managed ClamAV, TLS/secret management,
encrypted/versioned object storage, backup validation and institution-approved retention/legal-hold
rules. Large Insights rebuilds need asynchronous orchestration and paginated snapshots. GovHousing,
GovAssets and GovPetitions remain future business modules from the product brief.
