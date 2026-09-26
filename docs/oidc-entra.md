# Microsoft Entra ID / institutional OIDC configuration

GovControl implements provider-neutral OIDC Authorization Code Flow with PKCE. No Entra-specific
SDK is required.

No identity-provider container is bundled into the default stack. The cryptographic OIDC contract
is exercised against an isolated test provider (real RSA signing, discovery, JWKS and token
exchange), while local product E2E uses the server-only development identity. This avoids treating
a demo realm and demo passwords as a production security baseline. A separately operated Keycloak
realm can use the same settings when an interactive local SSO demonstration is required.

## Identity-provider registration

1. Register a confidential web application for the GovControl gateway.
2. Configure the exact callback, for example
   `https://govcontrol.institution.example/auth/callback`.
3. Enable authorization code flow; do not enable an implicit token flow.
4. Issue the standard `openid`, `profile` and `email` scopes.
5. Ensure the ID token includes stable subject, email, email verification status and display name.
6. Provision the corresponding GovControl user with the issuer + subject mapping. Avoid automatic
   email linking in production.

## GovControl environment

Set:

```text
APP_ENV=production
AUTH_MODE=oidc
OIDC_ISSUER=https://login.microsoftonline.com/<tenant-id>/v2.0
OIDC_TRUSTED_ISSUERS=https://login.microsoftonline.com/<tenant-id>/v2.0
OIDC_CLIENT_ID=<application-client-id>
OIDC_CLIENT_SECRET=<secret-manager-reference>
OIDC_REDIRECT_URI=https://govcontrol.institution.example/auth/callback
PUBLIC_BASE_URL=https://govcontrol.institution.example
PORTAL_ORIGINS=https://govcontrol.institution.example
PORTAL_AFTER_LOGIN_URL=https://govcontrol.institution.example/legal
COOKIE_SECURE=true
COOKIE_SAMESITE=lax
FEDERATED_EMAIL_LINKING_ENABLED=false
```

Use the exact issuer returned by OIDC discovery. A multi-tenant Entra registration needs an explicit
tenant-to-GovControl provisioning policy and must not accept arbitrary issuers.

## Validation checklist

- discovery issuer exactly matches configuration;
- callback URI exactly matches both Entra and GovControl;
- wrong issuer/audience, expired tokens, replayed state and wrong nonce are rejected;
- inactive/unprovisioned users are rejected by Platform;
- logout deletes the GovControl Redis session;
- no OIDC token appears in browser Web Storage, application logs or audit payloads.
