# Phase 14 - locally verified release preparation

17 October 2026. The access-control and deployment-preparation implementation is
verified locally. **The original phase also requires actual cloud deployment and
production smoke; those remain incomplete.** No resources were provisioned, no
image was pushed, and no live-provider/customer outcome was verified.

## What changed

- Production FastAPI operations authenticate a server bearer token before routing
  or body processing, enforce exact configured Host, reject browser Origins/cookies
  as credentials, and bound authenticated request bursts. Missing configuration
  stays locked. Provider secrets and the new service token are masked, and the
  service token is included in the model/tool secret-echo guard.
- Authenticated history/policy/provider reads and bounded investigation can run in
  production when explicitly configured. Fixture modes remain rejected. The fixed
  registry has 12 production read tools, excluding the synthetic browser fixture;
  local mode retains 13. Investigation defaults off. Incident creation remains
  opt-in and requires configured access/storage. Production retry/recovery remain
  disabled, with no HTTP/model approval/execution/verification/resolution writes.
- Next.js production mode has an operator login using a generated high-entropy
  access key, constant-time digest comparison and an eight-hour HMAC session bound
  to the operator digest and canonical HTTPS origin. The signed cookie is Secure,
  HttpOnly, SameSite=Strict and host-only. Each data handler and the server-rendered
  dashboard enforce access. Exact Host/Origin checks resist forwarded-host changes;
  login/logout/investigation require JSON and matching Origin. Service credentials
  remain server-side on a fixed HTTPS connection, never a browser proxy parameter.
- Invalid production configuration fails frontend startup; Vercel rejects local
  mode. Security headers and no-store API behavior accompany existing response,
  question, byte/schema/time limits. The investigation route declares 130 seconds
  to cover its bounded 125-second backend fetch. Per-instance login throttling is
  explicit and does not claim distributed protection.
- `/health` remains process liveness only. Backend `/ready` reports readiness only
  when production access is configured and application storage has the current
  migration revision. It waits at most three seconds, reuses a pending worker and
  drains it during shutdown. It never migrates or polls providers. Disabled,
  unreachable or unmigrated storage is not ready. Frontend `/api/health` is process
  liveness only.
- The production backend entry point requires access configuration and PostgreSQL,
  runs one worker with bounded concurrency, rejects proxy-header authority, disables
  access logs and allows 180 seconds shutdown draining. Non-loopback application
  PostgreSQL still requires verify-full TLS; an optional validated mounted project
  CA supports provider certificates without disabling hostname verification.
- Backend/frontend multi-stage Dockerfiles use non-root runtime users, health
  commands, narrow contexts, hash-pinned Python requirements and `npm ci`/Next.js
  standalone output. Environment templates, a non-echoing local key generator,
  explicit migration/startup instructions, local TLS smoke and deployed acceptance
  script are included. No application schema or existing `.env` was changed.

Read [DEPLOYMENT.md](DEPLOYMENT.md) for actual commands, hosting settings, security
tradeoffs, rollout, health behavior and rollback. The concrete suggested topology
is Vercel frontend, a Docker-compatible backend such as Render, and dedicated
Supabase PostgreSQL storage; no account/provider resources were selected or created.

## Frontend priority completed in this phase

At the user's direction, frontend quality was handled first. The product is a web
application. `/` now introduces it through a charcoal/green landing page, original
workflow diagram, four selectable illustrative stages, concrete product explanation
and links to `/dashboard`. The dashboard and incident drawer share the same palette.
The homepage makes no provider/model calls and executes no actions. Examples are
explicitly illustrative; no uptime statistics, testimonials or customer outcomes
are invented. See [FRONTEND-REFINEMENT.md](FRONTEND-REFINEMENT.md).

The real in-app browser verified stage selection, homepage-to-dashboard navigation,
synthetic recorded history, incident drawer open/close, dark surfaces and no
horizontal overflow at actual measured widths 1309px and 355px. No browser
error/warning logs were observed. A viewport screenshot was saved; full-page
capture was unavailable. Browser overrides were reset and the local preview remains
at `http://127.0.0.1:3001/` while its supervised process is running.

## Verification

- **974 backend tests passed, no skips, in 343.21 seconds.** This is 47 more than
  Phase 13, including authentication before adapter access, Host/Origin/header
  ambiguity, disabled production mode, absent writes, model secret guarding,
  request budgets, live-schema readiness, worker cancellation/draining, custom CA
  validation and production startup policy. The full suite includes real isolated
  PostgreSQL variants, SQLite and six real Chromium cases.
- PostgreSQL used a validated stopped project-test cluster copy with a fresh
  scratch database/password; the harness stopped its own server. The source cluster
  and application database were not modified. The prior fresh-initdb environment
  problem remains unestablished; the validated copy fallback was used.
- **20 frontend tests passed**, including signed-session expiry/tampering/audience,
  key rotation, duplicate cookies, fixed HTTPS configuration, Host/Origin/CSRF,
  server credential forwarding/stripping and login budgets, plus existing gateway,
  evidence, observation/source/staleness and approval-state tests.
- ESLint, TypeScript and the release webpack/standalone build pass. The complete
  npm audit has **zero known vulnerabilities** at verification time. No new npm
  dependencies were added. Ruff lint/format pass for **118 Python files** and
  `pip check` reports no broken requirements.
- The actual standalone Next.js server and real Uvicorn pass production-mode HTTP
  smoke over verified disposable local TLS on both connections. HTTPX verifies
  against the disposable CA; Node adds that CA to its normal trust store. Certificate
  rejection is enabled, not bypassed. Login, cookie flags, logout, authenticated
  server forwarding, Host/Origin rejection, secret-safe data and absent remediation
  routes pass. No live provider/model calls are made.
- That HTTP harness intentionally disables production storage and verifies `/ready`
  returns **503**. It does not claim successful production PostgreSQL/Supabase TLS.
  Actual SQLite/PostgreSQL schema readiness is covered separately in the regression.
- The separate actual backend HTTP smoke passes. Final diff whitespace validation
  passes; ignored secrets, temporary certificates/databases, node_modules and
  build outputs are excluded from the local commit.

Evidence: ignored `work/logs/phase-14-*`,
`work/evidence/phase-14-local-production-smoke.json`,
`work/evidence/phase-14-npm-audit.json` and the stopped-cluster harness evidence.

Initial focused tests exposed a mock construction call that needed resetting before
checking adapter access. An oversized parameter's automatic pytest ID also exceeded
Windows temporary-name handling; explicit short test IDs corrected it. Formatting
issues were fixed. Failed intermediate runs are not counted as verification passes.

## Limits and remaining acceptance

This is a single trusted operator/organization release, without tenant isolation,
individual identities, MFA/SSO or server-side per-session revocation. Sign-out clears
the current browser cookie; copied sessions remain valid until expiry unless the
operator/signing key is rotated. Request budgets are per process; a public hosting
edge must add shared throttling, size/connection limits and TLS. The baseline CSP
permits Next.js inline bootstrapping/styles and is not nonce-based strict CSP.

Docker is unavailable here. Linux image builds, image scanning/digest promotion,
container execution and shutdown remain unverified. Actual Vercel/backend/Supabase
accounts/domains, dedicated-role grants, project CA/network behavior, edge limits,
live readiness and the prepared deployed-smoke script still need acceptance on
the selected infrastructure. Live providers/Nebius and business outcomes remain
unverified. No scheduler or automatic retry was added.

Remaining roadmap: **finish Phase 14 cloud/container acceptance, then Phase 15's
intentional-failure demo**. Do not label the project fully deployed, and do not
begin Phase 15 automatically. All new files, caches, databases, certificates and
logs in this session stayed on D:.
