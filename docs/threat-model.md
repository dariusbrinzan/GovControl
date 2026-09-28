# Gateway threat model

## Assets and trust boundaries

The protected assets are institutional records, tenant/RBAC context, OIDC tokens, GovControl
sessions, service credentials, document bytes and audit history. The browser is untrusted. The
gateway is the public API boundary. Platform is the identity and authorization authority;
GovContracts owns only its contractual domain; GovDocuments owns document metadata and bytes;
GovNotifications owns notification and delivery state.
GovInsights owns derived projections, report definitions and export artifacts; source services
remain systems of record.
Redis is trusted infrastructure for ephemeral
sessions, rate counters and append-only authentication events.

## Addressed threats

| Threat | Control |
| --- | --- |
| Browser forges tenant, user, role or permission | Identity headers are discarded; the gateway assertion contains signed IDs and Platform reloads RBAC. |
| Stolen browser storage | No access, refresh, development or assertion token is stored in Web Storage. |
| Session-cookie script access | Opaque cookie is HttpOnly, signed and backed by a revocable Redis record. |
| CSRF | SameSite cookie, origin validation and per-session CSRF token on every mutating proxied request. |
| Login replay | OIDC state is random, single-use and expires in Redis; nonce is verified in the ID token. |
| Authorization-code interception | PKCE S256 and exact configured redirect URI. |
| Forged OIDC token | RS256 allowlist, JWKS key selection, signature, issuer, audience, expiry and nonce checks. |
| Open proxy / SSRF | Fixed upstream URLs and explicit service/path/method route map; no caller-provided target. |
| Header smuggling / confused deputy | Small request/response header allowlists; cookies and caller authorization are not forwarded. |
| Resource exhaustion | Request-size limit, configurable fixed-window rate limit, pooled connections and timeouts. |
| Malicious document content | Allowlisted MIME/extensions, size/empty checks, quarantine states and mandatory ClamAV configuration in production. |
| Path traversal or object overwrite | Normalized display names and server-generated immutable UUID S3 keys; callers never choose storage keys. |
| IDOR/cross-tenant document access | Identity-derived tenant filters on every query plus authenticated HTTP ownership checks for every new link. |
| IDOR/cross-tenant notification access | Every inbox mutation filters both identity-derived tenant and recipient; delivery administration remains tenant-scoped and permission-gated. |
| Event payload leaks business content | Consumers copy only controlled UUID/action fields and render allowlisted versioned templates. |
| Duplicate or replayed events | Event UUID, tenant deduplication key and deterministic schedule key are persisted before Redis acknowledgement. |
| Browser invokes notification internals | Gateway has an exact notification path/method allowlist and does not route `/internal/*`. |
| Browser invokes Insights internals or legacy analytics | Gateway exact-routes Insights, blocks snapshots/internal paths and blocks migrated Platform search/analytics routes. |
| Cross-tenant report/search access | Identity-derived tenant predicates apply to every projection, report, run and export lookup; foreign object IDs return 404. |
| Report builder becomes arbitrary SQL | Resource types, filters, columns and sort directions are server allowlisted and compiled by the service. |
| Spreadsheet formula injection | CSV/XLSX cells beginning with formula-control characters are neutralized before export. |
| Sensitive source data enters analytics | Event and snapshot schemas retain controlled metadata only; document bodies and unrestricted producer payloads are never indexed. |
| Stale or replayed projection update | Event UUID ledger plus source version/event time ordering prevents duplicate and older writes. |
| Poison event stalls the stream | Pending recovery, bounded exponential retry, tenant-scoped DLQ inspection and audited retry. |
| Unauthorized or permanent export URL | Objects use generated keys; bytes are returned only after owner/admin authorization and expire with worker cleanup. |
| SMTP credential disclosure | Secret types, metadata-only logs and no channel configuration API; production validates complete SMTP settings. |
| Concurrent metadata overwrite | Required `If-Match` ETag and row locking reject stale changes. |
| Premature deletion | Retention date blocks soft delete; bytes and audit remain recoverable. |
| Credential leakage in telemetry | Logs contain method, path, status, duration and request ID only; auth audit hashes session IDs. |
| Stale or disabled account | Platform checks active tenant/user and reloads permissions for every assertion. |

## Residual and deployment risks

- TLS termination, encryption at rest, WAF/DDoS capacity and Redis/PostgreSQL network policy belong
  to the target deployment environment.
- The HMAC gateway assertion and internal service credential must be injected from a secret manager
  and rotated. Workload identity or mTLS is the preferred later replacement.
- Email auto-linking is disabled by default and must remain disabled in production unless the
  institution has a reviewed account-provisioning policy. Pre-provision issuer + subject mappings.
- Redis authentication, encrypted transport and persistence policy must be set for production.
- Production must operate and monitor ClamAV rather than the development-only clean scanner.
- SMTP reputation, bounce processing, recipient policy and provider quotas remain production
  responsibilities; EMAIL stays disabled by default and WEBHOOK is rejected.
- Storage encryption, object lock/WORM, physical purge approvals and tamper-resistant external
  audit archival remain deployment/compliance responsibilities.
- Insights rebuild transport is synchronous locally. Large production tenants require a dedicated
  orchestrator, paginated snapshots, capacity limits and monitored SLOs.
