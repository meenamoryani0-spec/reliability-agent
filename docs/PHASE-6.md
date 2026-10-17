# Phase 6 — Read-only infrastructure checks

Implemented and locally verified on 17 October 2026. Stop after this phase.

## Implemented

| Check | Operation and interpretation |
| --- | --- |
| Vercel deployment | GET `/v13/deployments/{idOrUrl}` for one configured ID; verify identity and normalize readyState |
| Vercel build events | GET `/v3/deployments/{idOrUrl}/events`, backward, follow=0, limit=25, builds=1; retain only type/timestamp |
| Supabase project | GET `/v1/projects/{ref}`; verify reference and provider project state |
| Supabase service health | GET `/v1/projects/{ref}/health?services=db,auth,rest&timeout_ms=2000`; require all requested services once, with consistent status/healthy |
| PostgreSQL | Fixed `SELECT 1, current_setting('transaction_read_only')`; require `(1, 'on')` |

FastAPI exposes `GET /services/infrastructure` and
`POST /checks/infrastructure/{check_id}` for five fixed check IDs. POST runs a
read check; it does not modify provider resources. Disabled/fixture/live modes
are explicit. Missing credentials do not block local development.

## Verification

- Recovered unchanged baseline: **245 tests passed**, lint/format passed.
- Final regression: **360 tests passed**, including **115 new Phase 6 tests** and
  all six existing real Chromium tests. Ruff lint/format passed.
- `scripts/infrastructure-smoke.ps1`: PASS through a real local Uvicorn/FastAPI
  process, with HTTPX provider mocks and a fake PostgreSQL driver connection.
- Combined smoke with `--infrastructure --n8n --browser`: PASS; health HTTP 200,
  five infrastructure checks, four n8n fixture reads, two real Chromium flows.
- Psycopg **3.3.6**, bundled libpq **18.4**; hashed dependency locks. Existing
  dependency versions were retained; Psycopg/binary and tzdata were added.
- Installed libpq accepts the exact connection parameters via make_conninfo.
  A real Python child process rejects malformed input without echoing it.

Evidence: ignored `work/evidence/infrastructure-smoke.json` and
`work/evidence/phase-6-combined-smoke.json`. The fixture reports deployment ERROR,
one stderr event, healthy Supabase project/db/auth/rest, and a successful
synthetic database probe. All results explicitly mark synthetic=true, root
cause/business outcome unverified. Event health stays UNKNOWN.

**No real cloud resource or SQL server was contacted.** PostgreSQL uses a fake
driver returning the expected fixed-query result. This does not verify real
database connectivity, certificate acceptance, SQL execution or provider health.

Tests cover documented GET paths/parameters, authentication, Host/SNI/pinning,
private/mixed DNS rejection before credentials are sent, access/rate/transport
failures, deadlines, JSON/content-type/size limits, resource identity, transient
states, incomplete/duplicate/contradictory health, sanitized event sampling,
credential echo rejection, environment parsing, production rejection, fixed SQL,
read-only policy, worker isolation, timeout termination and cleanup.

## Boundaries

- HTTP hosts are fixed official endpoints with public DNS/IP validation,
  pinned addresses and original Host/SNI. No proxies, redirects, retries or
  automatic pagination. Deadline defaults to 10 seconds (1–30 configurable),
  decoded response limit 1 MiB, event sample limit 25. Unknown schemas fail.
- Inspection success is separate from health. Access/transport/configuration
  errors are CHECK_FAILED, healthy=null; they do not establish a broken service.
- Deployment READY concerns one configured deployment, not the currently
  promoted production alias or booking delivery. Event samples cannot establish
  runtime health/root cause. Only Supabase db/auth/rest health is requested.
- PostgreSQL accepts a registered public DNS host on 5432/6543. Psycopg was
  chosen for libpq's documented host/hostaddr separation: pin the validated IP
  while preserving the hostname for TLS verification.
- Live database probes run in a separate Python process. Credentials enter via
  stdin, never command-line arguments. Unrelated provider secrets, PG settings
  and proxy environment variables are excluded. Errors do not echo raw input.
- TLS is verify-full with the pinned Certifi bundle; client certificates and
  integrated authentication are disabled. Only password/SCRAM is accepted.
  Private/self-signed databases need a future explicit network/CA policy.
- Caller deadline includes DNS/startup. Worker communication gets the remaining
  budget. Timeout triggers the existing tested process-tree cleanup, with up
  to ten seconds for cleanup. The slot stays held until cleanup completes.
- The only query is static; read-only startup settings, statement/lock timeouts
  and the returned read-only setting are checked. This does not restrict the
  login's permissions elsewhere; use a dedicated least-privilege login.
- Provider log text, environment data, request metadata, database names/users,
  passwords and raw exceptions are discarded. Production inspection routes
  remain disabled until deployment access controls are built.

## Recovery investigation

A minimal asyncio startup reproduced the old stall. A timed stack trace showed
Windows `_fallback_socketpair` blocked in socket.accept during event-loop
creation, before app code. Granting sandbox network permission made the same
command and unchanged baseline pass. No application/event-loop bypass was added.

Backend HTTP smoke caught a dotenv string-port parsing issue, now covered by a
settings validator/regression test. PostgreSQL process isolation prevents a
stalled driver from relying solely on server-side query timeouts.

## Official contracts checked on 17 October 2026

- [Vercel deployment endpoint](https://vercel.com/docs/rest-api/deployments/get-a-deployment-by-id-or-url)
- [Vercel build events](https://vercel.com/docs/rest-api/deployments/get-deployment-events)
- [Vercel OpenAPI](https://vercel.com/openapi.json)
- [Supabase Management API](https://supabase.com/docs/reference/api/introduction)
- [Supabase official OpenAPI](https://api.supabase.com/api/v1-json)
- [Psycopg connection API](https://www.psycopg.org/psycopg3/docs/api/connections.html)
- [Psycopg event-loop compatibility](https://www.psycopg.org/psycopg3/docs/advanced/async.html)
- [PostgreSQL connection parameters and TLS](https://www.postgresql.org/docs/current/libpq-connect.html)

Official specifications/pages are saved in ignored `work/reference/phase-6/`.

## Remaining work

Live Vercel/Supabase/PostgreSQL, Nebius and n8n connections remain unverified.
No application persistence schema, tool registry, agent loop, incidents,
remediation, recovery workflow, frontend, GitHub push or deployment was added.

Next: **Phase 7 — database persistence**, following the saved plan.
