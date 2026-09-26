# GovControl implementation status

Status reviewed on 2026-09-25 against the initial project brief and the GovContracts extraction
goal.

## Delivered boundaries

| Boundary | Ownership | Runtime |
| --- | --- | --- |
| Platform/GovLegal | tenants, identity, RBAC, organization, GovLegal, shared document metadata | FastAPI `:8000` |
| GovContracts | complete contractual domain, local audit, notifications and outbox | FastAPI `:8010` |
| GovContracts worker | outbox publication and due-date notification generation | independent worker |
| Portal | common institutional shell and module user interfaces | Next.js `:3000` |
| Gateway/BFF | OIDC/local login, Redis sessions, CSRF, routing and edge policy | FastAPI `:8080` |
| Infrastructure | PostgreSQL, Redis Stream and S3-compatible object storage | Docker Compose |

GovContracts owns the `contracts` PostgreSQL schema and its Alembic history. It never imports
Platform code or queries Platform tables. Platform validates contract document ownership through
an authenticated internal HTTP contract. Organizational references are validated in the opposite
direction through Platform's internal directory contract.

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
- Local/S3 document adapter; Compose uses externally persisted S3-compatible storage.
- Liveness, dependency readiness, graceful worker shutdown and restart policies.
- One-shot, independently versioned migration containers gate API/worker startup.

## Verification evidence

- GitHub Actions independently enforces lint, strict type checking and tests for Platform,
  GovContracts, gateway and the portal, followed by the portal production build.
- Platform: Ruff, strict mypy and 27 pytest tests.
- Gateway: Ruff, strict mypy and 13 pytest security/integration tests.
- GovContracts: Ruff, strict mypy and 8 pytest tests.
- Portal: ESLint, strict TypeScript, 4 Vitest tests and optimized Next.js build with 20 routes.
- Alembic autogeneration checks report no missing operations for either chain.
- Clean temporary database verified Platform + GovContracts upgrade, full downgrade and upgrade.
- Idempotent GovContracts seed verified stable contract and document counts across repeated runs.
- Real Playwright flows cover GovLegal dashboard/cases and GovContracts dashboard/registry/detail,
  workflow controls and audit against host services and the containerized stack.
- Container smoke tests cover readiness, authenticated internal calls, tenant-reference rejection,
  outbox delivery and document upload/download through S3.

## Intentional future work

No Kubernetes or Helm manifests are maintained now, per the current product decision. Containers
remain portable through stateless APIs, external persistence, environment configuration, probes
and graceful shutdown. Add deployment manifests only for a concrete target environment.

A dedicated document service and notification service remain target boundaries rather than empty
microservices. An actual institutional OIDC tenant must still be registered using the documented
Entra/Keycloak-compatible configuration. GovHousing, GovAssets and GovPetitions remain future
business modules from the product brief.
