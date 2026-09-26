# GovDocuments extraction audit

Audit performed on 2026-09-26 before changing the document boundary.

## Repository and baseline

- Baseline commits: Gateway/SSO `9ab4474`; final session and tenant hardening `f2b0b9e`.
- The pre-existing local change to `docs/implementation-status.md` is preserved.
- Platform passed Ruff, strict mypy, 28 pytest tests and `alembic check`.
- GovContracts passed Ruff, strict mypy, 8 pytest tests and `alembic check`.
- Gateway passed Ruff, strict mypy and 13 pytest tests.
- Portal passed ESLint, TypeScript, 4 Vitest tests and the 20-route production build.
- The running Compose baseline was healthy with the portal on `:13000` and gateway on `:18080`.

## Existing ownership and data

Platform currently owns `public.documents`, its ORM model, repository, API, service and both the
filesystem and S3 adapters. The table has foreign keys to Platform tenants and users, so it is not
an independent service boundary. GovContracts owns no document rows and calls Platform document
routes through the portal.

The development database contains six rows for one tenant: one Contract, one CourtDecision, one
EnforcementProceeding, one LegalCase and two LegalObligation attachments. All six checksums are
syntactically valid and storage keys are unique. Their bytes exist in `data/documents`, while the
currently configured S3 bucket contains no objects. A backfill therefore has to support a legacy
filesystem source and must verify bytes/checksums before cutover; copying metadata alone would
produce broken downloads.

## Current request flows and risks

- Browser document calls use `/api/v1/platform/documents`; Gateway has no GovDocuments upstream.
- Upload reads the complete file into memory before hashing and storage.
- Downloads read the complete object into memory before returning a `StreamingResponse`.
- Platform checks legal resource ownership by directly querying its legal repository.
- Contract ownership is checked over an authenticated HTTP call to GovContracts.
- Each validation creates a new `httpx.AsyncClient`; no shared connection pool is used there.
- Only the broad `legal.manage` or `contracts.manage` permissions protect document operations.
- The current model has no versions, links table, lifecycle/scan state, classification, retention,
  soft deletion, optimistic concurrency, document-local audit or outbox.
- Filename, MIME and empty-content validation are insufficient; storage keys are nevertheless
  generated from tenant/document UUIDs and the existing adapters reject path traversal on reads.

## Infrastructure and trust baseline

- SeaweedFS exposes an S3-compatible bucket and persists bytes in a named Compose volume.
- Redis provides sessions and the shared event stream.
- Gateway has an explicit route/method allowlist, strips browser identity headers, applies CSRF,
  rate/body limits and issues a short-lived signed identity assertion.
- Platform Identity remains the tenant/RBAC authority through hidden authenticated HTTP contracts.
- GovContracts owns the `contracts` schema and a separate Alembic version table; this is the model
  for the new `documents` schema and migration chain.
- Default Compose keeps Platform and GovContracts internal. The debug override publishes their
  ports only on `127.0.0.1`.

## Extraction invariants

1. No browser call may bypass Gateway.
2. GovDocuments may use only explicit authenticated HTTP contracts to validate identity or owners.
3. Every query and storage key remains tenant scoped; browser tenant/role headers are untrusted.
4. Existing rows and bytes remain untouched until an idempotent, verified backfill succeeds.
5. New writes cut over only after GovLegal and GovContracts use the independent service.
6. Platform keeps a compatibility/read-only legacy path during validation and removes it only in a
   later cleanup migration; this goal does not destructively drop the source data.
7. No Kubernetes or Helm artifacts are introduced.
