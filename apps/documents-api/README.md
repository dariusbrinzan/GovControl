# GovDocuments

GovDocuments is the independently buildable document boundary for GovControl. It owns the
`documents` PostgreSQL schema, document metadata and versions, resource links, lifecycle state,
audit history, transactional outbox and all S3-compatible object access. It never queries
Platform/GovLegal or GovContracts tables.

## Local commands

From the repository root:

```bash
make documents-migrate
make documents-dev
make documents-worker
make documents-check
```

The API listens on `127.0.0.1:8020` only when run directly or through the debug Compose override.
Normal browser traffic uses `http://127.0.0.1:8080/api/v1/documents` through Gateway.

## Processing flow

1. Gateway authenticates the browser session, enforces CSRF/limits, strips identity headers and
   signs a short-lived internal assertion.
2. GovDocuments validates the assertion, reloads tenant/RBAC context from Platform Identity and
   validates the linked resource through an authenticated internal HTTP contract.
3. The request is streamed into a bounded spool while size, filename, MIME and SHA-256 are checked.
4. Bytes are written under a server-generated `tenant/document/version` S3 key. Metadata, audit
   and outbox are committed together.
5. `local_clean` makes validated local-development uploads immediately available. Production must
   configure ClamAV; uploads remain quarantined until the worker marks them available or rejected.
6. Only `AVAILABLE` versions can be streamed back through Gateway.

See [`../../docs/govdocuments.md`](../../docs/govdocuments.md) for HTTP contracts, events,
retention, recovery, migration and verification evidence.
