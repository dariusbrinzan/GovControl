# GovDocuments operations and contracts

## Ownership and data model

GovDocuments exclusively owns schema `documents` and its `alembic_version_documents` history:

- `documents`: tenant-scoped classification, retention, lifecycle, current version and optimistic
  `lock_version`;
- `document_versions`: immutable filenames, MIME, byte size, SHA-256, scan result and generated S3
  key;
- `document_links`: explicit links to the seven supported resource types;
- `audit_events`: actor, action, request ID and non-binary details;
- `outbox_events`: versioned integration events with at-least-once publication;
- `idempotency_records`: tenant-scoped upload request keys and request hashes.

The allowed resource types are `LegalCase`, `LegalObligation`, `CourtDecision`,
`EnforcementProceeding`, `Contract`, `ContractAmendment` and `ContractMilestone`. Their existence
and tenant ownership are checked only through authenticated Platform or GovContracts HTTP calls.

## Public HTTP contract

All public calls start at Gateway `/api/v1/documents`; the service itself is private in normal
Compose mode.

| Method and path | Permission | Purpose |
| --- | --- | --- |
| `GET /` | `documents.read` | tenant-scoped search, state/resource filters and pagination |
| `POST /` | `documents.upload` | multipart upload; supports `Idempotency-Key` |
| `GET /{id}` | `documents.read` | metadata and current version; returns `ETag` |
| `GET /{id}/versions` | `documents.read` | immutable version history |
| `POST /{id}/versions` | `documents.upload` | new version; requires `If-Match` |
| `GET /{id}/download?version=` | `documents.read` | streamed available-version download |
| `PATCH /{id}` | `documents.manage` | metadata change; requires `If-Match` |
| `POST /{id}/links` | `documents.manage` | validate and add a business link |
| `DELETE /{id}/links/{link_id}` | `documents.manage` | remove a link |
| `POST /{id}/archive` | `documents.manage` | archive without deleting |
| `DELETE /{id}` | `documents.delete` | retention-aware soft delete |
| `POST /{id}/restore` | `documents.delete` | restore a soft-deleted record |
| `GET /{id}/audit` | `documents.audit` | document-local audit history |

`tenant_id`, roles and permissions are never accepted from browser input. Unknown or cross-tenant
IDs return the same not-found response. Gateway forwards only its signed assertion, request ID and
a narrow header allowlist.

## Events

The worker publishes JSON envelopes to `govcontrol.events`. Delivery is at least once and consumers
must deduplicate using envelope `id`. Envelopes include event type, tenant ID, aggregate ID,
occurrence time and metadata identifiers, never document bytes.

Current types are `document.uploaded.v1`, `document.available.v1`, `document.rejected.v1`,
`document.version_created.v1`, `document.archived.v1`, `document.deleted.v1` and
`document.restored.v1`.

## Retention policy

`retention_until` is an optional business retention date. A document cannot be soft-deleted before
that date; metadata managers may set or explicitly clear it using an ETag-protected update. Soft
delete hides metadata and download from normal reads but deliberately preserves versions and S3
objects for restoration and audit. Physical purge is not automated in this phase. Before enabling
purge in production, the institution must define legal-hold precedence, approval, minimum audit
retention, object-lock/WORM requirements and a two-person purge procedure.

## Recovery and backup

Back up PostgreSQL and the S3 bucket as one recovery set, with object versioning enabled by the
production storage provider. To recover:

1. stop GovDocuments API and worker writes;
2. restore the database to a point-in-time and restore the corresponding bucket generation;
3. run `alembic upgrade head` and `alembic check`;
4. compare every current version's object size and SHA-256 with `document_versions`;
5. start the API, verify `/health` and `/ready`, then start the worker;
6. replay unpublished outbox rows; consumers deduplicate event IDs;
7. perform an authenticated upload/download checksum smoke before reopening traffic.

If metadata exists but an object is missing or has the wrong checksum, keep the document
unavailable, restore the object from backup and record the incident. Do not replace bytes under an
existing key with different content.

## Legacy backfill and rollback

Platform's exporter reads the legacy owner and verifies source checksums. GovDocuments backfill
preserves document IDs, creates deterministic first-version IDs, generates target S3 keys, checks
the target checksum and records links/audit/outbox. Repeating the same manifest skips verified
rows. The validated local run imported and verified all 6 legacy rows; a second run imported 0,
skipped 6 and verified 6.

Legacy rows and filesystem bytes are intentionally retained. Rollback is therefore: stop new
document writes, point the portal/Gateway back to the prior release, re-enable the legacy router,
and retain the `documents` schema/bucket for reconciliation. Documents created after cutover need
an explicit reverse export before a rollback that must preserve them; there is no unsafe automatic
dual-write.

Run the two phases with an absolute export directory (the second command is safe to repeat):

```bash
make documents-export-legacy DOCUMENT_EXPORT_DIR=/tmp/govcontrol-documents-export
make documents-backfill DOCUMENT_EXPORT_DIR=/tmp/govcontrol-documents-export
```

## Performance observations

These are local smoke results, not production benchmarks:

- clients are process-scoped: one pooled `httpx.AsyncClient`, one pooled S3 client and one Redis
  client per process;
- uploads are chunked, SHA-256 is incremental and the second-stage spool rolls to disk after 2 MiB;
- a test at its configured 3 MiB maximum confirmed disk rollover, and eight concurrent spool jobs
  retained independent checksums;
- on 2026-09-26, four concurrent 24 MiB uploads through Gateway completed with four `201` responses
  in 3.75 seconds wall time (individual 3.73–3.75 seconds). During the run, observed container RSS
  was about 58 MiB for Gateway and 133 MiB for GovDocuments. The test records were soft-deleted.

Real sizing still requires representative storage latency, file mix, ClamAV capacity, TLS and
production CPU/memory limits.

The live browser suite uses `make web-test-e2e-live`. Its development-only cleanup removes records,
audit/outbox rows, published Redis Stream messages and S3 objects identified by the reserved
`e2e-` filename prefix or the `PERFORMANCE_SMOKE`/`SMOKE_TEST` categories before and after the run.
The cleanup refuses outside `APP_ENV=development`.
