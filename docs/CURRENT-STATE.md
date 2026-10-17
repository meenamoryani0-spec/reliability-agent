# Current implementation state

Updated 17 October 2026 after verified Phase 13.
Repository: `D:\CODEX MAIN\2026-10-09\g\outputs\reliability-agent`.
Read this file and the phase report. HANDOFF.md retains the original roadmap;
its initial CURRENT STATE is historical.

Phases 1–11 provide the backend, monitoring adapters, real Chromium synthetic
flows, SQLite/PostgreSQL history, 13 bounded read tools, bounded investigation,
automatic unhealthy-check incidents and a separately approved one-shot n8n retry.
Phase 12 adds local operator verification of the exact accepted new execution.
Phase 13 adds the local Next.js dashboard; deployment, automatic provider retry
and a scheduler remain outside the current implementation.

The dashboard has Overview, Incidents, Checks, Activity and Connections views,
bounded backend investigation, linked sanitized evidence, supported hypotheses,
recommendations, source/status/search filters, approval/action audit, and exact
historical recovery proof. Desktop/mobile and explicit loading/empty/error states
are verified. Records are bounded to the latest 100 per collection. Refresh reads
history; observations older than five minutes are marked stale. No provider
credentials, arbitrary proxy, browser approval/retry/verification/resolution route,
or production identity are added. Run scripts/frontend-demo.ps1 for a fresh,
explicit synthetic fixture preview, or frontend-run.ps1 alongside run.ps1 for the
existing backend. Read frontend/README.md and docs/PHASE-13.md.

Recovery defaults off: `N8N_RECOVERY_MODE=disabled`, `N8N_RECOVERY_FLOWS={}`.
Enabling requires non-production access, migrated storage, matching n8n mode,
configured required node IDs/completion node, and credentials in live mode.
`python -m app.recovery.cli verify --action-id UUID` makes one bounded GET through
the existing pinned HTTPS n8n client. No HTTP resolve/verify/approval route or AI
write tool exists. `/recovery` describes policy; `/history/verifications` and
`/history/verifications/{UUID}` are bounded local audit reads.

An ACCEPTED retry receipt still does not establish recovery. Verification requires
same source/mode/synthetic identity, workflow, exact new ID, retry lineage,
terminal success, present execution data, fresh timestamps, explicit success in
every required node attempt and the configured completion node observed last.
The configured path must cover every original failed node and complete beyond
it. Absent, redacted, oversized, contradictory, stale or unfinished evidence
cannot resolve. One successful retry cannot close other executions grouped in
the same incident. Each attempt is audited as VERIFIED, NOT_RECOVERED or
INCONCLUSIVE. Read-history commit and verification transaction are separate;
check-save failure cannot resolve, and proof-save failure retains the check.

Only successful verification atomically stores proof and resolves the incident.
Resolution scope is **n8n_required_nodes**, not global service/customer recovery.
Root cause remains unknown/null and business_outcome_verified remains false:
a successful confirmation node is not proof of delivery. Repeated verification
returns the immutable historical proof with a reuse flag, not a fresh health
claim. Polling the original historical failure reuses its resolved incident;
a different failed execution opens a new one. Per-service locking serializes
incident linking and resolution; SQLite uses BEGIN IMMEDIATE. Worker cancellation
and shutdown drain pending work; no provider writes occur in verification.

Migration head: **0005_verified_recovery**. The database requires a VERIFIED
same-incident proof referencing a same-service healthy check before resolution.
SQLite's explicit migration connection temporarily disables incoming FKs only
for its batch rebuild under a write lock, checks all FKs before commit, and restores
enforcement on every exit. Normal application connections retain enforcement.
Downgrade refuses to discard any recovery audit; no reset/retry/delete endpoint
exists. Startup never runs migrations. Preserve the one-shot retry approval,
expiry, source binding and uncertainty safeguards from docs/PHASE-11.md.

Phase 13 regression: **927 passed, no skips** in 357.04 seconds, including 149
isolated PostgreSQL variants and six real Chromium cases. The frontend adds 13
passing tests; lint, TypeScript, release build, full npm audit (zero known
vulnerabilities), and real built frontend/backend/Chromium smoke pass with zero
browser runtime errors. Ruff lint/format (111 files), pip and actual backend HTTP
smoke pass. Phase 12's development database upgrade and CLI/Uvicorn restart
evidence remain in docs/PHASE-12.md; Phase 13 does not change that database or
the existing .env. Live Nebius/model tool calling,
n8n reads/retry/recovery, Vercel, Supabase and monitored/cloud PostgreSQL remain
unverified. Synthetic execution success does not establish customer outcomes.
The separate application store is tested on real isolated local PostgreSQL.

Two roadmap phases follow Phase 13: **14 deployment/access controls**, and
**15 intentional-failure demo**. Stop after the verified local Phase 13
commit until the user authorizes the next phase. Keep all artifacts on D:;
do not push, deploy, add a remote/license or alter provider secrets.
