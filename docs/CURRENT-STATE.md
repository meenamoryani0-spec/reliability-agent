# Current state — 20 October 2026

This page supersedes older phase-status statements. Historical implementation
reports remain in PHASE-*.md, RENDER-ROLLOUT.md and VERCEL-ROLLOUT.md.

## What is deployed and verified

- Frontend: https://reliability-agent.vercel.app/dashboard on Vercel.
- Backend: https://reliability-agent-josr.onrender.com on Render Free.
- History: Supabase PostgreSQL, private reliability schema, restricted runtime
  role, verified TLS. Schema head: 0006_operator_targets.
- Single-operator login, authenticated backend calls, history persistence and
  logout passed live HTTPS acceptance.
- hdworks.tech is saved persistently. Two consecutive automatic cycles completed
  at 11:28 and 11:33 UTC on 20 October and each saved healthy HTTP, DNS and TLS
  checks. No manual Run checks request was used for the second-cycle proof.
- The backend website timer is enabled with a 300-second interval after each
  cycle. It runs only while the single backend process is running. Free-host
  sleep, restarts and network failures can leave gaps; there is no backfill.
- Automatic incident recording is enabled for persisted unhealthy observations.
  Incident behavior passed controlled local fixtures; no production failure was
  manufactured. Healthy checks cannot automatically close incidents.
- A GitHub Actions workflow checks the fixed public backend /ready and frontend
  /api/health URLs. Its initial push-triggered run passed. Its approximately
  five-minute schedule is best effort; scheduled execution was not yet observed
  at this verification point. This is application readiness, not provider or
  business-outcome verification. See DEPLOYMENT.md for limitations.
- A website URL can be saved in Overview, then checked with Run checks.
  Refresh records only reloads history. Results become stale.

## What remains unconnected

- n8n public API: disabled. The supplied Cloud instance is a free trial. n8n's
  official help center says that trial instances cannot use the public API.
- Infrastructure monitoring: disabled. A provider login used to deploy the app
  does not give the backend a management token. Application storage credentials
  are separate from monitored database credentials.
- AI investigation: disabled. Nebius is optional for the personal-use project;
  neither it nor an alternative provider has passed a live inference test. Groq
  Free was researched as a candidate, but this user's account/key access was not
  established. No model-provider billing was activated or inference key created.
- Production remediation, retry and recovery: disabled. Local CLI behavior is
  separately tested; there are no production approval/dispatch/resolve routes.
- Real customer browser flows are not configured. Synthetic fixtures are labeled
  and run only in the local demo, never as proof of live business outcomes.

The connected n8n app available to this Codex chat can read the user's workflows.
Those chat credentials are not a deployed backend integration. Historical failed
executions do not prove the current workflow version is still failing.

## Current verification milestone

PR #1 merged the website timer, schedule status, bounded public deployment probe,
and continuous integration. Both final CI jobs passed, including backend tests
and real loopback HTTP smokes plus frontend checks, build and Chromium acceptance.
The backend and frontend run that merged code. A fresh deployed HTTPS
login/storage acceptance test also passed after the production frontend rollout.

The overview now explains Website, n8n, Infrastructure and Reliability Agent,
shows configuration separately from evidence, and says when AI and incidents are
off. The landing page is a product introduction, not the live dashboard.

An actual live navigation bug was reproduced: a cross-site top-level link to
/dashboard returned 404 rather than reaching sign-in. HTML page handlers now
allow document navigation after the exact Host/Origin checks; API requests,
iframes and mutations retain their cross-site denial. Session validation remains
required before rendering the dashboard.

An optional free Error Trigger receiver is implemented behind
N8N_EVENTS_ENABLED=false. It accepts only registered workflow/execution IDs under
a separate ingest-only token, deduplicates immutable history and can link
incidents when that policy is enabled. It does not poll the public API or retain
customer payloads. No new migration is required. Read FREE-N8N-REPORTING.md.

The user's approved reporter is active in the n8n Personal project at its root.
A dedicated ingest-only credential is stored privately in n8n and Render. The
error handler is attached to hdworksAI tele, Operations Telegram Bot, and Employee
Website Intake. Their business nodes, connections, published version IDs and
unrelated draft differences were verified preserved.

A separate isolated test workflow failed through its production webhook and
invoked the reporter in error mode. The real HTTP request was accepted, persisted,
and displayed in the authenticated dashboard. The test workflow was deactivated
and archived; its temporary allowlist entry was removed. The final backend
allowlist contains the three business workflows. The saved test observation is
test evidence, not proof of a business workflow failure. On 20 October the reporter
was rechecked as active with its published version matching its draft; no business
workflow was executed or modified. ID-only reporting does not establish failed-node
detail or root cause. New qualifying reports can create incidents under the now
enabled backend policy; that path was not retested with a production failure.

This is a partially connected product, not a completed live reliability loop.
Do not claim complete integration coverage, continuous monitoring, AI diagnoses
or repair work until their separate live acceptance tests pass.

## Architecture in ordinary language

Vercel serves the screen. Render runs the checks and investigator. Supabase saves
this app's evidence and history. The website, n8n and monitored infrastructure are
inputs to the backend. An explicitly configured AI provider would supply the
model; none is currently enabled. The frontend does not receive provider secrets.
