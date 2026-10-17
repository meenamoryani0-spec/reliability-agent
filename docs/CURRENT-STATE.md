# Current implementation state

Updated 17 October 2026 after Phase 10.

Repository: `D:\CODEX MAIN\2026-10-09\g\outputs\reliability-agent`.
Use this file, phase evidence documents and Git history for current progress.
The original HANDOFF.md contains historical requirements; its initial CURRENT
STATE/NEXT STEP no longer describe implementation progress.

- Phase 1: verified FastAPI foundation.
- Phase 2: Nebius/Nemotron client, mock-tested; live use unverified.
- Phase 3: HTTP/DNS/TLS checks; saved local and example.com smoke evidence.
- Phase 4: real Chromium with intercepted synthetic booking fixtures.
- Phase 5: read-only n8n adapter; sanitized evidence and provider fixtures.
- Phase 6: Vercel deployment/events, Supabase project/services and a fixed
  PostgreSQL monitoring probe. Provider connectivity remains unverified.
- Phase 7: SQLAlchemy models, explicit Alembic migrations and application history.
- Phase 8: strict registry of 13 existing monitoring tools, bounded internal
  dispatch, normalized evidence/history. Local catalog only; production disabled.
- Phase 9: bounded model/tool investigation loop, local GET /agent and POST
  /investigations, validated evidence-linked conclusions, explicitly scripted
  model fixtures and opt-in live Nebius path. Investigation defaults off.
- Phase 10: opt-in automatic incidents from persisted UNHEALTHY observations.
  Database-enforced service/kind deduplication, unique evidence links, incident
  detail/observation/assessment reads, supported diagnosis/recommendation persistence
  and confirmed IDs/save outcomes in investigation reports.

Final Phase 10 regression: **720 passed, no skips**, including **112 new cases**,
all **72 isolated PostgreSQL variants**, SQLite and six real Chromium cases.
Ruff lint/format and pip checks pass; 87 checked Python files are formatted.
Actual Uvicorn incident/restart smoke passed: 15 checks, 3 synthetic incidents,
7 linked unhealthy observations, 3 supported assessments, no duplicate incidents,
identical IDs/evidence across restart. The model was scripted; providers were fixtures. The older
storage smoke passed with detection disabled: 9 checks, 8 services, 0 incidents.

`INCIDENTS_ENABLED=false` remains the default and the development setting.
When enabled, existing direct checks and investigation tools automatically open
or reuse one unresolved incident per service identity/check kind. UNKNOWN,
CHECK_FAILED, DEGRADED, HEALTHY and lists never open incidents. Detection uses
server policy, not model prose or an incident-write tool. Root cause and business
outcome remain unverified. Severity high is a policy default, not measured impact.

Counts represent check observations, including repeated polling of the same
execution, not affected bookings or users. Different causes on one service/kind
share an unresolved incident. No scheduler, reconciliation/retry queue, public
incident write route, remediation or recovery workflow exists. Healthy checks do
not resolve incidents; RESOLVED remains database-rejected. Production enablement
and history reads stay disabled pending authentication/access controls.

Migration head is **0003_incident_assessments** after **0002_incident_detection**. Startup never migrates. Valid
legacy incidents keep IDs/initial evidence and gain a link; unsafe duplicate or
non-unhealthy legacy incidents block migration before DDL without data deletion.
Existing checks alone are not retroactively converted into incidents.

The ignored local development database `work/data/reliability.sqlite3` was
backed up via SQLite's backup API and explicitly migrated from 0001 through 0002 to 0003.
It had 0 services/checks/incidents. Backup/database integrity, foreign keys and
original column values passed verification. Backup stays in work/backups on D:.
The ignored .env and provider settings are unchanged; no dependencies were added.
Application storage remains separate from monitored POSTGRES_* credentials.

Check history commits before incident detection. Incident/link creation is
atomic; its failure preserves the check and reports incident unavailable.
Capture workers drain on cancellation/shutdown. A deadline can return unknown
persistence before a worker later commits; returned IDs only confirm completed
transactions. A failed detection has no automatic historical reconciliation.

The Phase 9 investigation still permits 6 model requests, 8 tools, 120 seconds,
and one investigation in flight. Registry arguments/results remain bounded to
4 KiB/64 KiB; slots remain occupied until underlying timed-out work completes.
Conclusions require supported evidence citations; no model prose is treated as
verified cause. Incident IDs/creation flags now derive from actual captures;
remediation, root-cause and business-outcome verification flags remain false.
Only validated final conclusions add assessments for cited checks that themselves
support the hypothesis and are already linked to an incident. The repository
rechecks support against stored evidence and rejects fixture assessments on real
observations. Finite recommended steps, inference provenance, check IDs and
creation times persist; root cause stays null/unknown and database-guarded.
Assessment-save failure preserves check, incident and validated conclusion while
reporting its separate unavailable outcome. Invalid conclusions add no diagnosis.
Pending assessment workers keep the registry/investigation slots occupied and
drain on cancellation/shutdown. Investigations themselves are not persisted as
new database records; only their supported incident assessments are stored.

Live Nebius model availability/tool calling, n8n, Vercel, Supabase and cloud/
monitored PostgreSQL remain unverified. Synthetic evidence is not proof of live
provider behavior or customer outcomes. The Phase 6 monitored PostgreSQL probe
uses driver fixtures; application storage is separately tested on real PostgreSQL.

SQLAlchemy 2.0.55 and Alembic 1.20.0 remain locked. Portable EDB PostgreSQL 18.6
binaries are under ignored work/postgres-runtime. The unchanged integration
harness runs on an isolated loopback cluster and stops it afterward; no Windows
service or cloud/customer database is used. Phase 8's earlier initdb timeout
cause remains unverified; Phase 9 and Phase 10 harness runs pass here.
All new files, databases, backups, caches, logs and evidence stay on D:.
No remote, push, deployment or license change has been added.

**Phase 10 is complete. Next: Phase 11 — first approved write (bounded n8n retry).**
Five phases remain (11–15): approved remediation, recovery verification,
frontend, deployment/access controls and demo. Stop after Phase 10; do not begin
Phase 11 without the user's next phase instruction. Read docs/PHASE-10.md before
continuing and preserve fixture/live distinctions and evidence safeguards.
