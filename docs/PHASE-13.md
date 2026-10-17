# Phase 13 — local reliability dashboard

Completed and verified locally on 17 October 2026. The Next.js frontend connects
to the existing backend; live provider/model availability and customer outcomes
remain unverified. No deployment, push, new remote, or license change occurred.

## Result

`frontend/` provides a responsive Next.js 16.4.2, React 19.3.1, TypeScript 6.0.3,
Tailwind 4.3.3 workspace. Geist/Geist Mono, a graphite sidebar, muted green
surfaces, and real recorded signal strips support five working views:

1. Overview: recent health signals, open incidents, uncertainty/staleness, pending
   approval, service observations, investigation, and recovery policy.
2. Incidents: status filter and native accessible evidence drawer, diagnosis,
   recommendations, linked observations, approval/action state, and recovery proof.
3. Checks: status/source/search filters, age, and sanitized evidence disclosures.
4. Activity: approval/dispatch audit, uncertain outcomes, historical verification.
5. Connections: backend/storage/investigation/retry/recovery policy and limitations.

The investigation form calls the existing bounded backend investigation. Fixture
mode is explicitly scripted and supports only its known booking question. Results
show evidence citations, hypothesis, suggested steps, provenance and budgets.
Live mode warns that restricted evidence/question go to Nebius. No credentials
are copied into the frontend or sent as browser configuration.

Lists/metrics reflect at most the latest 100 records per collection, with at most
eight overview service/check signals. Counts are observations/incidents in that
window, not customers or global totals. Refresh reads stored history; it does not
poll providers. Relative ages update locally. Evidence older than five minutes,
or more than five seconds ahead, is stale and excluded from recent healthy counts.
Configured but unobserved systems are never counted as healthy.

The built frontend uses three fixed local API handlers: dashboard reads, exact
incident details, and bounded investigation. Response bodies, schemas, counts,
timeouts, question bytes, and keys are bounded. Fetches are no-store and reject
redirects; the server accepts only operator-configured loopback backend origins.
Local host/origin checks reject remote hosts and cross-site requests; investigation
also requires explicit same-origin JSON. No arbitrary backend path/URL proxy exists.

Approval, retry execution, recovery verification and resolution remain operator
CLI operations. The UI displays their actual audit states and a help reference.
Expired/uncertain actions are not reset or resent. An ACCEPTED receipt does not
close the incident. Proof is fetched by the incident's exact verification ID and
displayed as historical, limited to `n8n_required_nodes`. Customer delivery and
root cause remain unverified, including after scoped resolution.

Disabled storage, unavailable backend/policy, missing diagnosis, empty filters,
failed refresh, loading, disabled/busy/incomplete investigation, expired approval,
and inconclusive/missing verification are explicit. Source text is rendered as
escaped data, not HTML. Native dialog focus trapping and Escape dismissal work;
reduced-motion preferences are supported. `/` focuses search outside inputs/dialogs.

## Verification

- **927 backend tests passed, no skips, in 357.04 seconds**, including the existing
  149 isolated PostgreSQL variants and six Chromium cases. The validated stopped
  project-test cluster was copied; fresh scratch credentials/database were used;
  the harness stopped its server. Source cluster and application database were
  not modified. Fresh initdb's earlier unresolved environment issue is unchanged.
- **13 frontend tests passed**, covering origin/host/configuration boundaries,
  streamed byte limits, schema errors and secret-safe failures, partial history
  failure, strict questions, false success claims, observation ordering, source
  identity, stale/future timestamps, approval expiry and literal search.
- ESLint/React Hooks, release webpack build, TypeScript and dependency tree pass.
  The **full npm audit has zero known vulnerabilities** at verification time.
- Ruff lint and formatting pass for **111 Python files**; pip check passes.
  `scripts/test.ps1` now includes the entire scripts directory in Python linting.
- Actual built Next.js -> Uvicorn -> scratch SQLite -> fixture provider/CLI smoke
  passes with **real Chromium and zero browser runtime errors**. It verifies
  desktop 1536px/mobile 390px overflow, source/search/status filters, evidence
  disclosures, modal dismissal, scripted investigation, unexpired approval,
  ACCEPTED while OPEN, exact-node proof before RESOLVED, recovery scope, and
  empty/disabled-storage/offline states. It also rejects remote Host, cross-origin
  and originless POSTs and confirms absent HTTP remediation routes.
- The separate actual backend HTTP smoke passes. Desktop, incident, and mobile
  screenshots were captured and visually inspected; CSS animations were disabled
  for deterministic screenshots, not for the running application.

Evidence is in ignored `work/logs/phase-13-*`,
`work/evidence/phase-13-frontend-smoke.json`,
`work/evidence/phase-13-npm-audit.json`, and `work/evidence/phase-13-*.png`.

## Issues found and corrected

- Windows intermittently returned EPERM during concurrent recursive directory
  creation in npm and Next.js. The local frontend environment loads a narrow
  generated-directory retry helper for `.next/` and `node_modules/`. It retries
  only that error, leaves unrelated paths/errors intact, and changes no global
  Node, Windows, or antivirus settings. Underlying cause remains unestablished.
- Initial framework lint tooling introduced an advisory in a glob dependency.
  It was replaced with current ESLint/TypeScript/React Hooks tooling; the final
  complete dependency audit is clear. No forced framework downgrade was used.
- Browser smoke found Next.js's internal localhost URL differing from the browser
  loopback Host. Origin validation now checks the validated loopback Host while
  also requiring an internal loopback URL. Added tests cover both representations.
- Initial lint/type errors and an ambiguous smoke selector were corrected. The
  final build/tests/smoke pass; failed intermediate runs are not claimed as passes.

## Run and remaining scope

See `frontend/README.md`. Use `scripts/frontend-demo.ps1` for a populated synthetic
preview, or `scripts/run.ps1` plus `scripts/frontend-run.ps1` for existing backend
configuration. The preview explicitly migrates a new disposable SQLite database,
records fixture checks and a scripted assessment, and plans a pending CLI action.
It never executes a live provider write and does not change the existing `.env`
or application database. Ctrl+C stops its supervised processes.

These local host/origin checks are not production authentication. **Two roadmap
phases remain: 14 deployment/access controls, and 15 intentional-failure demo.**
Stop after the verified local Phase 13 commit. Do not begin Phase 14, push, or
deploy without the user's next instruction. Live Nebius/model/tool calling,
n8n/provider behavior and customer delivery still require validation.

Official references inspected: [Next.js installation](https://nextjs.org/docs/app/getting-started/installation),
[route handlers](https://nextjs.org/docs/app/getting-started/route-handlers),
[fetch caching](https://nextjs.org/docs/app/api-reference/functions/fetch).
