# Reliability dashboard — Phase 13

A local Next.js/TypeScript workspace for the existing FastAPI backend. A graphite
navigation rail, quiet green accents, Geist typography, recorded signal strips,
and an evidence drawer organize the operational workflow. All chart bars represent
actual loaded observations; no uptime percentages or invented trend data are shown.

## Run against your configured backend

From the repository root in PowerShell:

```powershell
.\scripts\frontend-setup.ps1
.\scripts\run.ps1
# In another terminal:
.\scripts\frontend-run.ps1
```

Open <http://127.0.0.1:3000>. The server defaults to the backend on
`http://127.0.0.1:8000`. For another local backend port, set
`RELIABILITY_BACKEND_URL` in the frontend process environment or copy
`frontend/.env.example` to `frontend/.env.local`. Do not copy provider keys into
the frontend environment. The backend's existing `.env` is separate and preserved.

Node >=20.9 is required (verified with Node 24.16.0). Dependencies are pinned in
`package.json` and `package-lock.json`. The environment scripts place npm, Node,
Next.js, temporary files, and browser artifacts on D:, and disable Next telemetry.
On other operating systems, ordinary `npm ci`, `npm run dev`, `npm run build`,
and `npm run start` work from `frontend/`; the defaults bind to loopback.

## Populated synthetic preview

```powershell
# Install dependencies and Chromium first if not already available:
.\scripts\frontend-setup.ps1
.\scripts\browser-install.ps1
.\scripts\frontend-check.ps1
.\scripts\frontend-demo.ps1 -Port 3000
```

The explicit preview creates a **new scratch SQLite database**, runs an explicit
migration, starts its own loopback backend, and collects real local fixture
observations, including a real Chromium synthetic booking check. It uses the
existing scripted investigation, records one failed booking execution, and plans
an action through the existing operator CLI. It does **not** execute the action or
contact live providers. Synthetic sources are labeled throughout. Approval expires
after five minutes; expiry is displayed without changing the audit record.

Ctrl+C stops the supervised preview servers. Scratch data/logs remain in ignored
`work/` for inspection. This preview is a frontend fixture, not a verified live
integration or the Phase 15 customer demonstration.

## Behavior and boundaries

- Overview: recent healthy signals, open incidents, uncertain/stale observations,
  unexpired approvals, service signals, and bounded investigation.
- Incidents: status filters, linked evidence, supported hypotheses, recommended
  steps, action audit, and exact historical recovery proof.
- Checks: sanitized evidence, statuses, source labels, observation timestamps.
- Activity: approval/dispatch state, uncertain outcomes, and stored verification.
- Connections: backend/storage/investigation/action/recovery policy and limits.
- Search and source filters apply to loaded records. `/` focuses search outside
  inputs/dialogs. Escape closes the native modal and returns focus.
- Refresh only reads persisted records. No background checking or provider polling
  is introduced. Relative ages update locally every 30 seconds.
- Each history collection loads **at most the latest 100 records**. Metrics and
  lists describe that window, not global totals. Overview displays at most eight
  latest service/check signals. An older configured service with no loaded check
  is not silently classified healthy. Older records remain in the backend.
- Evidence older than five minutes or more than five seconds ahead is marked
  stale. The five-minute display threshold is separate from backend recovery
  freshness requirements.
- Disabled storage, missing assessments, offline backend, empty results, request
  failures, busy/disabled investigation, expired approval, and inconclusive proof
  are explicit states. Connection errors never become unhealthy service claims.
- Fixture investigation supports only “Why are booking confirmations missing?”.
  Live investigation sends restricted evidence and the question to Nebius; the
  input warns against secrets/customer data. No model output becomes verified cause.
- Browser requests reach three fixed server handlers. The server reads a fixed
  operator-configured loopback backend origin. No arbitrary URL/SQL/shell proxy,
  credential forwarding, redirect following, or remediation route exists.
- Approval, retry, verification and resolution stay in existing local operator
  interfaces. The browser shows audit state and a CLI help reference, not an
  approval button. ACCEPTED never implies recovered; stored proof is historical
  and limited to `n8n_required_nodes`. Business outcomes/root cause stay unverified.
- This is **local-only**. Run scripts bind both servers to loopback; API handlers
  reject non-loopback hosts, cross-site requests, and nonlocal deployment mode.
  Investigation additionally requires matching Origin and JSON, validates strict
  bounded input, and makes at most the existing backend's bounded investigation.
  Response bytes, time, schemas, and arrays are bounded. No-store reads and
  anti-framing headers apply. These are not production identity/access controls;
  Phase 14 must implement and verify those before deployment.

## Verification

```powershell
.\scripts\frontend-check.ps1
.\scripts\frontend-smoke.ps1
```

Frontend checks run Node tests, ESLint/React Hooks rules, release build, TypeScript,
and the runtime dependency audit. The browser smoke uses the built Next.js server,
real Uvicorn, fresh SQLite, fixture providers, the actual operator CLI, and Chromium.
It verifies filters, incident evidence, keyboard dismissal, investigation, receipt
versus recovery, scoped proof, mobile layout, and empty/disabled/offline states.
Logs/screenshots/evidence are written to ignored `work/`. No credentials needed.

On this Windows workspace, concurrent generated-directory creation intermittently
returned EPERM. `scripts/frontend-fs.cjs`, loaded only by frontend environment
scripts, retries that error for `.next/` and `node_modules/` with a synchronous
recursive fallback. It preserves unrelated paths/errors. The underlying Windows
cause remains unestablished; no system, antivirus or global Node settings changed.

Official framework references checked during implementation:
[installation](https://nextjs.org/docs/app/getting-started/installation),
[route handlers](https://nextjs.org/docs/app/getting-started/route-handlers),
[fetch caching](https://nextjs.org/docs/app/api-reference/functions/fetch).

## Product homepage and dashboard

The root `/` is the product introduction: charcoal/green visual identity,
interactive illustrative workflow, product explanation, operating boundaries and
links to the application. `/dashboard` is the operational workspace. Both share
the same palette. The homepage makes no provider requests; its stage controls
only explain the example and never execute checks or actions.

## Authenticated deployment mode

Read `../docs/DEPLOYMENT.md`. Production mode uses a generated operator key,
eight-hour signed secure cookie, exact configured HTTPS origin and server bearer
authentication to a fixed HTTPS backend. Data handlers enforce session access
individually. The public homepage has no operational data; `/dashboard` requires
sign-in. `/login` redirects to the dashboard in local mode.

The release includes standalone output and an optional non-root Dockerfile.
The local production-mode TLS smoke runs the actual standalone server. Vercel
requires explicit production configuration and canonical origin; do not use
production secrets in preview deployments. A public deployment and Linux Docker
image execution remain unverified.
