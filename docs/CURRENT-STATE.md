# Current implementation state

Updated 17 October 2026 after Phase 11.
Repository: `D:\CODEX MAIN\2026-10-09\g\outputs\reliability-agent`.
Use this file, phase reports and Git history. HANDOFF.md's initial CURRENT
STATE/NEXT STEP are historical; its original phase requirements remain context.

- Phases 1–6: FastAPI, bounded Nebius client, HTTP/DNS/TLS checks, real Chromium
  synthetic flows, read-only n8n and infrastructure adapters. Live model/providers
  remain unverified; website local/example.com evidence is saved in earlier phases.
- Phase 7: SQLAlchemy/Alembic application history, separately configured from
  monitored POSTGRES_* credentials; SQLite and real isolated PostgreSQL tested.
- Phase 8: fixed registry of 13 bounded read/observation tools; no public execution.
- Phase 9: bounded model/tool investigation with supported evidence citations;
  scripted fixture and separately opt-in live Nebius mode. Investigation defaults off.
- Phase 10: opt-in automatic incidents from persisted UNHEALTHY checks, unique
  service/kind deduplication/evidence links, supported assessment/recommendation
  persistence and bounded incident reads. Root cause stays explicitly unknown.
- Phase 11: separate local operator CLI for one approved n8n retry per original
  source/execution, with durable proposal/approval/dispatch/receipt audit.

Final Phase 11 regression: **819 passed, no skips** (161.50 seconds), including
**99 new cases**, all **98 isolated PostgreSQL variants**, SQLite and six real
Chromium cases. Ruff lint/format pass for **97 Python files**; pip check passes.
Actual CLI/Uvicorn smoke passed with a fresh scratch SQLite database: missing
approval blocked, one accepted synthetic retry/audit record, repeat execution
blocked before/after backend restart, new execution 2001 reported running,
incident remained OPEN. No live n8n write was performed.

The initial 720-case baseline rerun exposed a timing-sensitive test whose 20 ms
storage timeout expired before the fixture reached storage. That test now allows
one second while an event still forces the intended storage timeout. Product
limits were unchanged. The final complete regression passes without skips.

Retry defaults disabled: N8N_RETRY_MODE=disabled, N8N_RETRY_WORKFLOW_IDS=[].
Enablement requires non-production access, migrated storage, matching n8n modes,
allowlisted workflow IDs and live credentials when applicable. Planning uses a
stored unhealthy error execution linked to an unresolved incident, captured
within five minutes. It makes no provider request. The proposal names the exact
check/incident/execution/workflow/source and warns of possible duplicate effects.

The local CLI requires explicit --approve-retry-side-effects for that action ID.
It consumes approval atomically before provider I/O. Source/mode/workflow/expiry
are rechecked; a fresh provider read validates the original failed execution and
no recorded retry ancestor/success. Dispatch intent must commit before a fixed
POST with loadWorkflow=false. The model has no retry tool and HTTP has no action
approval/execution route. The local OS operator is trusted; this is not production
identity authentication or proof a workflow is idempotent.

Unique source/execution records and conditional claims prevent this application's
same-database retries from dispatching twice. External operators may act outside
that guarantee. There are no automatic retries, bulk writes or reset endpoints.
A timeout/invalid receipt after dispatch is UNKNOWN. A failed final audit write
leaves EXECUTING blocked; an abandoned intent can remain there after a crash.
Do not reset/retry such records automatically. Worker cancellation/shutdown drains
pending work before engine disposal; an in-flight POST cannot be revoked.

ACCEPTED means a validated new-execution receipt, not a successful fix or recovery.
Recovery/business-outcome flags stay false. Incidents remain OPEN/INVESTIGATING;
RESOLVED is still database-rejected. GET /actions is local policy metadata;
GET /history/actions and /history/actions/{UUID} are bounded local audit reads.
Production action enablement/history access remain rejected pending controls.

Migration head: **0004_approved_n8n_retry**. Startup never migrates. The new table
references linked incident evidence and constrains approval/state/receipt
consistency. Nonempty legacy check/incident preservation is tested on both engines.
The ignored local development SQLite file was backed up and explicitly upgraded
from 0003 to 0004. Its five prior data tables were empty. Integrity, foreign keys,
backup and prior values passed verification; retry remains disabled. The ignored
.env/provider settings, dependencies and locks are unchanged. Backup stays on D:.

Phase 10 behavior remains: only persisted UNHEALTHY checks open incidents;
HEALTHY/DEGRADED/UNKNOWN/CHECK_FAILED/lists do not. Synthetic/live/source identities
stay distinct. Counts are observations, not affected users/bookings. Different
causes on a service/kind share one unresolved incident. Only cited individually
supported conclusions can add finite hypotheses/recommendations. Root cause is
null/unknown and database-guarded; HTTP 401 cannot establish credential expiry.
No scheduler, historical reconciliation or automatic resolution exists.

The investigation still permits six model calls, eight tools, 120 seconds and
one investigation in flight. Registry JSON is bounded to 4 KiB input/64 KiB
output. Slots remain occupied until timed-out underlying work drains. Model
prose is never verified cause. Its remediation flag stays false because operator
actions are separate; supported incident assessments are persisted, full
investigations are not. Phase 10's actual restart smoke had 15 checks, 3 incidents,
7 linked observations and 3 supported assessments with no duplicates.

Live Nebius model availability/tool calling, n8n reads/retry, Vercel, Supabase and
cloud/monitored PostgreSQL remain unverified. The separate monitored PostgreSQL
probe still uses driver fixtures; application storage is tested on real local
PostgreSQL. Synthetic evidence does not verify customer outcomes.
The unchanged portable PostgreSQL harness creates an isolated loopback cluster
and stops it afterward; no Windows service or cloud/customer database is used.
SQLAlchemy 2.0.55, Alembic 1.20.0 and EDB PostgreSQL 18.6 remain unchanged.
All new files, caches, databases, backups, logs and evidence stay on D:.
No remote, push, deployment, license change or unrelated laptop change was made.

**Phase 11 is complete. Next: Phase 12 — recovery verification before resolution.**
Four phases remain: 12 recovery verification, 13 frontend, 14 deployment/access
controls, 15 demo. Stop here until the user's next phase instruction. Read
`docs/PHASE-11.md` before continuing; preserve approval and uncertainty safeguards.
