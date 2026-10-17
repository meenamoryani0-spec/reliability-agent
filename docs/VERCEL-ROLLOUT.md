# Single-project Vercel frontend — 18 October 2026

Import only the `frontend` directory as a standalone Next.js project. Vercel's
root-directory Services detection is not the intended topology: the backend is
already on Render and passed public HTTPS/readiness/authenticated-storage checks.
No multi-service `vercel.json`, second backend or new database is needed.

## Origin and credentials

An explicit `RELIABILITY_PUBLIC_ORIGIN` still takes precedence. When it is absent
on Vercel production (`VERCEL=1`, `VERCEL_ENV=production`), the app uses the one exact
`VERCEL_PROJECT_PRODUCTION_URL` hostname, restricted to an assigned `.vercel.app`
DNS label. System environment variables must be enabled. Missing/malformed metadata
fails closed. Preview deployments, request Host, forwarded headers and wildcard
values cannot configure this origin. Custom domains require explicit configuration.
[Vercel system variables](https://vercel.com/docs/environment-variables/system-environment-variables).

Five project settings are prepared privately: production mode, the verified fixed
Render backend URL, its existing service token, an independent session signing key,
and the operator access key's SHA-256 digest. The raw operator key stays local.
Only server-side variables are used; none are prefixed `NEXT_PUBLIC_`. Credentials
must be scoped to Production, not shared with preview/development deployments.
[Vercel environment scopes](https://vercel.com/docs/environment-variables).

The local clipboard helper validates the saved configuration, creates independent
random keys only once, and reuses them on subsequent runs. The ignored state file
inherits a protected Windows DACL granting the current account and SYSTEM access.
No existing `.env`, backend token, database role/password or deployed secret was changed.

## Verification

- All **26 frontend tests passed**, including six new production-metadata cases:
  canonical origin, explicit-setting precedence, deployment-environment gating,
  invalid metadata, exact Host/Origin checks and signed-session audience binding.
- ESLint, TypeScript, Next.js production standalone build on Node 24.16.0 and runtime
  npm dependency audit passed; the audit reported zero vulnerabilities.
- Real standalone Next.js/Uvicorn local TLS smoke passed operator login, secure
  signed cookies/logout, backend bearer authentication, Host/Origin guards, no
  browser service-secret exposure and no HTTP remediation routes. That harness
  intentionally disables storage and requires readiness 503.
- The generated five-value bundle validates against the actual frontend config
  code. Its backend token matches the working Render token; its login digest
  matches the local operator key, which is absent from the upload bundle.
- Windows private-folder permissions and unchanged credentials on rerun passed.

Actual Vercel image/function execution, production-domain login and dashboard
acceptance are still pending. A local build is not evidence of a hosted frontend.
Keep the Hobby plan. Do not start Phase 15 or enable live model/provider/retry modes.
