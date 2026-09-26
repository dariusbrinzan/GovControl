# Secret rotation

Never copy `.env` into an image or production deployment. Generate unrelated random values and
inject them through the environment's secret manager.

## Development token

Change `DEV_AUTH_TOKEN`, then recreate Platform and gateway. Existing gateway sessions remain valid
until logout/expiry; flush Redis database 1 when immediate local invalidation is desired. This token
is forbidden when `APP_ENV=production`.

## Session signing secret

Changing `SESSION_SIGNING_SECRET` immediately invalidates every cookie signature. Recreate gateway
and delete keys matching `govcontrol:gateway:session:*`. Users must authenticate again. A future
dual-key verification window can be added when zero-interruption rotation is required.

## Gateway assertion secret

Change `GATEWAY_ASSERTION_SECRET` atomically for gateway and Platform, then recreate both. Assertions
live at most 60 seconds, so a coordinated rolling deployment may briefly reject requests. For a
multi-replica production rollout, add key IDs and overlapping verification keys first.

## Internal service token

Change `INTERNAL_SERVICE_TOKEN` for gateway, Platform, GovContracts and workers in one coordinated
operation. Readiness and smoke tests must confirm internal identity and document validation after
restart. Do not reuse this value for sessions or user authentication.

## OIDC client secret

Create the replacement credential at the identity provider, deploy it as `OIDC_CLIENT_SECRET`,
verify a complete login, then revoke the previous credential. Public PKCE clients may omit a client
secret, but the GovControl BFF should normally be registered as a confidential web application.
