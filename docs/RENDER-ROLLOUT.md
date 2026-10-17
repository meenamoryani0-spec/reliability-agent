# Free Render rollout preparation — 18 October 2026

The selected Supabase project has passed live explicit setup and restricted-account
verification at migration `0005_verified_recovery`. The administrator password was
entered privately and not retained. Generated runtime credentials are kept only in
an ignored Windows-account-restricted work folder; they are absent from this repository.

The backend now accepts Render's trusted `RENDER_EXTERNAL_HOSTNAME` as the one exact
allowed host when `RENDER=true` and `API_ALLOWED_HOSTS` is omitted. Explicit host
configuration takes precedence. Invalid/missing provider metadata fails startup;
request headers, forwarded headers and wildcard hostnames cannot configure access.
Both normal startup and the image health command use the same configuration function.
[Render metadata](https://render.com/docs/environment-variables).

The image includes the official public Supabase root CA, selected explicitly by
`STORAGE_SSL_CA_FILE=/app/backend/certs/supabase-ca.crt`. The build context adds only
that certificate; runtime secrets and work files remain excluded. PostgreSQL still
uses full certificate and hostname verification. Source and fingerprint are in
`backend/certs/README.md`.

## Validation

- The full backend run collected 989 cases: **988 passed, one failed**, in 324.44 s.
  The failure was the existing 20 ms timing case
  `test_slow_storage_returns_observation_while_slot_stays_busy`. The entire tool
  registry group subsequently passed separately: **79 passed in 5.83 s**. This is
  evidence of a timing-sensitive case, not a clean single-pass full-suite result.
  The registry implementation and its tests were not changed in this rollout.
- All 15 new Render-host cases passed during the full run, including explicit-host
  precedence, non-Render behavior, malformed metadata and hostile forwarded headers.
- The real standalone Next.js/Uvicorn production-mode local TLS smoke passed login,
  secure cookies/logout, server bearer authentication, Host/Origin checks, absent
  browser credentials and absent HTTP remediation routes. That harness deliberately
  disables storage and expects readiness 503.
- A separate real loopback HTTP smoke used the live restricted Supabase account.
  Readiness and authenticated history returned 200; unauthenticated history and
  browser-origin credentials returned 401; hostname substitution returned 400.
  The first readiness request returned 503 during connection initialization; the
  next returned 200. The actual image health Python command then passed. No
  monitoring, model, remediation or application-data write calls were made.
- The packaged certificate passed the pinned official DER fingerprint check.
- The local clipboard helper validated 16 settings without printing credentials.

## Still pending

Render's first Linux image build/run and cloud HTTP checks, frontend deployment,
edge configuration and the live Nebius/provider demonstration remain pending.
Local Python execution of an image health command is not a Linux container test.
No paid resources were provisioned and no existing `.env` was changed.

Keep the Render Free plan, repository-root Docker context, `backend/Dockerfile`,
default Docker command and `/ready` HTTP health path. Startup never migrates.
Investigation, incidents, retry/recovery and monitored providers remain disabled.
The free service can sleep; it does not establish continuous monitoring.
[Render Docker](https://render.com/docs/docker),
[HTTP health checks](https://render.com/docs/health-checks),
[free services](https://render.com/docs/free).
