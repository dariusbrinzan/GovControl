# GovControl implementation status

Status reviewed on 2026-09-26 against the initial project brief, GovContracts extraction,
gateway/SSO and GovDocuments extraction goals.

## Delivered boundaries

| Boundary | Ownership | Runtime |
| --- | --- | --- |
| Platform/GovLegal | tenants, identity, RBAC, organization and GovLegal | FastAPI `:8000` |
| GovContracts | complete contractual domain, local audit, notifications and outbox | FastAPI `:8010` |
| GovContracts worker | outbox publication and due-date notification generation | independent worker |
| GovDocuments | metadata, versions, links, lifecycle, audit, outbox and S3 access | FastAPI `:8020` |
| GovDocuments worker | malware scan transitions and document outbox publication | independent worker |
| Portal | common institutional shell and module user interfaces | Next.js `:3000` |
| Gateway/BFF | OIDC/local login, Redis sessions, CSRF, routing and edge policy | FastAPI `:8080` |
| Infrastructure | PostgreSQL, Redis Stream and S3-compatible object storage | Docker Compose |

GovContracts owns the `contracts` PostgreSQL schema and GovDocuments owns the `documents` schema;
both have independent Alembic histories. Neither imports Platform code or queries Platform tables.
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

- GitHub Actions independently enforces lint, strict type checking and tests for Platform,
  GovContracts, gateway and the portal, followed by the portal production build.
- Platform: Ruff, strict mypy and 29 pytest tests.
- Gateway: Ruff, strict mypy and 13 pytest security/integration tests.
- GovContracts: Ruff, strict mypy and 9 pytest tests.
- GovDocuments: Ruff, strict mypy and 26 pytest tests, including upload limits, spooling,
  unavailable states, S3 failures, RBAC, tenant/resource isolation and outbox shape.
- Portal: ESLint, strict TypeScript, 4 Vitest tests and optimized Next.js build with the document
  details/version/audit route.
- Alembic autogeneration checks report no missing operations for all three chains.
- A clean temporary database verified Platform, GovContracts and GovDocuments upgrade, full
  reverse-order downgrade and complete upgrade again.
- Idempotent GovContracts seed verified stable contract and document counts across repeated runs.
- Real Playwright flows cover GovLegal dashboard/cases, GovContracts dashboard/registry/detail,
  a restored contract mutation, workflow controls, audit, session logout and a revoked-session
  recovery against the containerized stack.
- Three real GovDocuments Playwright flows cover legal and contract upload, exact downloaded
  content, versions, audit, CSRF rejection, browser tenant-header stripping, soft delete and restore.
- A local concurrency smoke run completed 100 Redis-session requests and 40 authenticated
  Platform proxy requests without errors; the gateway reuses one pooled HTTP client.
- Container smoke tests cover readiness, authenticated internal calls, tenant-reference rejection,
  outbox delivery and document upload/download through S3.
- Four concurrent 24 MiB uploads through the real Gateway completed successfully in 3.75 seconds
  local wall time; observed RSS was about 58 MiB Gateway and 133 MiB GovDocuments. This is a smoke
  observation, not a production benchmark.

## Intentional future work

No Kubernetes or Helm manifests are maintained now, per the current product decision. Containers
remain portable through stateless APIs, external persistence, environment configuration, probes
and graceful shutdown. Add deployment manifests only for a concrete target environment.

A notification service remains a target boundary rather than an empty microservice. Production
still needs a real institutional OIDC registration, managed ClamAV, TLS/secret management,
encrypted/versioned object storage, backup validation and institution-approved retention/legal-hold
rules. GovHousing, GovAssets and GovPetitions remain future business modules from the product brief.
