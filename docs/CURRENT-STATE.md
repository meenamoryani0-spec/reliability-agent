# Current state — 19 October 2026

This page supersedes older phase-status statements. Historical implementation
reports remain in PHASE-*.md, RENDER-ROLLOUT.md and VERCEL-ROLLOUT.md.

## What is deployed and verified

- Frontend: https://reliability-agent.vercel.app/dashboard on Vercel.
- Backend: https://reliability-agent-josr.onrender.com on Render Free.
- History: Supabase PostgreSQL, private reliability schema, restricted runtime
  role, verified TLS. Schema head: 0006_operator_targets.
- Single-operator login, authenticated backend calls, history persistence and
  logout passed live HTTPS acceptance.
- hdworks.tech was saved and manually checked through the dashboard. Its HTTP,
  DNS and TLS checks passed at the time recorded in history.
- A website URL can be saved in Overview, then checked with Run checks.
  Refresh records only reloads history. Results become stale.

## What remains unconnected

- n8n public API: disabled. The supplied Cloud instance is a free trial. n8n's
  official help center says that trial instances cannot use the public API.
- Infrastructure monitoring: disabled. A provider login used to deploy the app
  does not give the backend a management token. Application storage credentials
  are separate from monitored database credentials.
- Nebius investigation: disabled. No provider key is configured in the known
  project environment. The signed-in account currently opens billing setup;
  credits and a usable key have not been verified. Spending remains at ₹0.
- Automatic incident creation: off in the last verified live configuration.
- Continuous scheduling: not implemented. Render Free may sleep.
- Production remediation, retry and recovery: disabled. Local CLI behavior is
  separately tested; there are no production approval/dispatch/resolve routes.
- Real customer browser flows are not configured. Synthetic fixtures are labeled
  and run only in the local demo, never as proof of live business outcomes.

The connected n8n app available to this Codex chat can read the user's workflows.
Those chat credentials are not a deployed backend integration. Historical failed
executions do not prove the current workflow version is still failing.

## Current repair milestone

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

An inactive reporter draft exists in the user's n8n Personal project at its root.
It was SDK-validated and tested with pinned synthetic data; the network request
was simulated. The three existing business workflows were not edited. Private
credential setup, approved attachment and live delivery acceptance remain pending.

This is a partially connected product, not a completed live reliability loop.
Do not claim all integrations, automatic monitoring, diagnoses or repair work
until their separate live acceptance tests pass.

## Architecture in ordinary language

Vercel serves the screen. Render runs the checks and investigator. Supabase saves
this app's evidence and history. The website, n8n and monitored infrastructure are
inputs to the backend. Nebius supplies the AI model when explicitly enabled with
credits. The frontend does not receive provider secrets.
