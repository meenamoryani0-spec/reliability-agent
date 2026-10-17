# Phase 10 — Automatic evidence-linked incidents

Implemented and locally verified on 17 October 2026. Stop after this phase.

## Behavior and policy

`INCIDENTS_ENABLED=false` is the default. Enabling it with migrated application
storage creates incidents automatically after **persisted UNHEALTHY checks**.
This applies to direct website/browser/infrastructure checks, n8n execution
details and the same observations collected through investigation tools.

The server decides from normalized evidence. The model cannot request arbitrary
incident writes, invent their IDs, establish root cause, or override this policy.
An invalid model conclusion does not discard an incident already created from
actual collected evidence. The existing 13-tool catalog remains unchanged.

- HEALTHY, DEGRADED, UNKNOWN and CHECK_FAILED never open incidents.
- List metadata never opens incidents or becomes check history.
- Deduplication key: service identity plus check kind, while OPEN/INVESTIGATING.
- Service identity retains component, source fingerprint and synthetic flag.
- Different causes within the same service/kind share an unresolved incident.
- Each unhealthy stored check links once; replaying its ID adds no duplicate link.
- Repeated checks add observations, even when polling the same n8n execution.
- `observation_count` is not a count of affected bookings, people or distinct events.
- New incidents start OPEN with policy severity high. Severity does not establish
  measured customer impact; existing severity/status/initial evidence are preserved.
- Healthy results do not resolve incidents. The database still rejects RESOLVED.
- Root cause, business outcome and recovery remain unverified.

There is no background monitoring scheduler. Automatic detection runs when a
check is executed through the existing backend/registry paths. No cross-service
causal correlation, alert delivery, approval/remediation or recovery workflow
is included in this phase. Production enablement is rejected pending controls.

## Persistence and migration

Current Alembic head: `0003_incident_assessments`, following
`0002_incident_detection` and `0001_history`.
Startup and HTTP routes never apply migrations. Run explicitly:

```powershell
.\scripts\migrate.ps1 -Action upgrade
.\scripts\migrate.ps1 -Action status
```

Migration 0002 adds incident check kind, an UNHEALTHY evidence discriminator,
composite evidence foreign keys, an unresolved service/kind unique index, and
`incident_observations`. The initial unhealthy check of each valid legacy
incident is backfilled as a link. Other historical checks are not scanned to
create incidents retroactively.

Before DDL, migration 0002 rejects legacy incidents referencing non-unhealthy evidence
or multiple unresolved incidents for the same service/kind. It does not silently
merge, delete or relabel history. Operator reconciliation would be required for
such legacy data. Both unsafe cases are tested to leave schema/history intact.
Back up before migration. Downgrade removes the new links and is destructive to
Phase 10 evidence; it is used only in disposable migration tests here.

Database constraints enforce same-service, same-kind unhealthy evidence, one
unresolved incident per key, and one incident link per check. SQLite incident
transactions acquire BEGIN IMMEDIATE before reading; PostgreSQL uses conflict
handling against the partial unique index. Concurrent detections cannot create
multiple unresolved incidents for the same key. Incident plus observation link
commit atomically. Check history commits separately first.

History capture tracks its worker through cancellation and drains it on shutdown
before disposing the engine. Existing bounded adapter/registry/investigation
slots still stay occupied until actual work completes.

## Supported diagnosis and recommendations

The original Phase 10 requirement includes diagnosis, severity, root cause,
evidence and recommendation persistence. An observed UNHEALTHY check is sufficient
evidence to record a detected problem immediately; inference must additionally
pass Phase 9's citation/support validation before adding a diagnostic assessment.
No numeric confidence score or established underlying cause is invented.

Migration 0003 adds `incident_assessments`. A valid final conclusion stores only
its cited check results that individually support its hypothesis and already
have confirmed incident links. Hypotheses and recommended steps use finite
vocabularies. The repository independently rechecks the hypothesis against stored
normalized evidence and rejects scripted-fixture provenance on real observations.
Each assessment references one linked unhealthy check through a database foreign
key; replay preserves its original diagnosis/recommendations rather than rewriting
history. Different check observations can retain successive assessments.

Assessments persist the hypothesis, recommended steps, inference source, creation
time and supporting check ID. Root cause is explicitly stored as null/unknown;
a database constraint rejects a claimed cause. HTTP 401 supports authentication
rejection, not credential expiry. Recommendations remain suggestions, not executed
actions. Direct failed checks can have an incident before inference and therefore
no diagnostic assessment yet. Invalid/unsupported conclusions add no assessment.

`incident_assessment` reports not_applicable, disabled, saved (with confirmed check
IDs), or unavailable independently of check/incident saves and model completion.
Assessment persistence uses a separate atomic bounded batch of at most eight
checks. Its failure preserves the incident, check and validated model conclusion.
Timeout/cancellation can leave a save pending; the registry/investigation owner
drains that worker and keeps slots occupied before shutdown. Migrations remain
explicit; 0003's downgrade drops the new assessment records.

## Responses and reads

Operational check response bodies retain their health evidence. Headers add:

| Header | Meaning |
| --- | --- |
| X-History-Status / X-Check-Id | Separate check-save outcome and confirmed ID |
| X-Incident-Status | disabled, not_applicable, created, existing or unavailable |
| X-Incident-Id | Present only after confirmed incident transaction success |

If saving the check fails, unhealthy incident detection is unavailable. If only
the incident transaction fails, the check remains saved and incident status is
unavailable. Neither failure changes operational health or exposes raw database
exceptions. A subsequent failed check may create/reuse an incident, but no retry
queue or reconciliation links the earlier missed observation automatically.

A registry response deadline can report unavailable while its worker later
commits. The response makes no confirmed creation claim in that case. Read the
stored incident history after completion; response flags are not an audit of
work still running after that response.

Investigation reports now include confirmed unique `incident_ids` and an
`incident_created` boolean computed from capture results. It is true if at least
one incident was confirmed newly created during that investigation. Reusing an
existing incident returns its ID and false. It can be true even when inference
later fails; collected evidence and server detection remain valid independently.

Read-only local routes:

- GET /history/incidents: existing pagination/service filter plus synthetic filter.
- GET /history/incidents/{UUID}: category/component/kind, derived title, initial
  evidence ID, state/severity, linked observation count and first/last observed time.
- GET /history/incidents/{UUID}/observations: linked normalized unhealthy checks.
- GET /history/incidents/{UUID}/assessments: persisted supported hypotheses,
  recommendations, inference source, check IDs and timestamps; root cause unknown.

Limits remain 1–100 rows and offset 0–10000. Missing UUID records return 404.
There are no public incident write/update/delete/resolve endpoints. History
reads stay disabled in production pending authentication/access controls.

## Verification

Baseline before implementation: **608 passed, no skips** on the isolated
PostgreSQL harness. Final regression: **720 passed, no skips**, including **112
new cases**, all **72 PostgreSQL variants**, SQLite and six real Chromium cases.
Ruff lint/format passed across 87 checked Python files. Pip reports no broken
requirements. No dependency changes were required.

Coverage includes concurrent detection of one check and many checks, replay,
source/synthetic/kind isolation, existing status/severity retention, out-of-order
observation times, atomic rollback, database constraints, valid/unsafe legacy
migration, restart durability, pagination, outage separation, cancellation
draining, production rejection, actual investigation reporting, invalid model
conclusions, pending/failed registry storage, assessment support/provenance,
recommendation persistence, assessment rollback and cancellation cleanup.

Verification exposed a PostgreSQL race between the initial-check unique
constraint and the unresolved service/kind index when concurrent workers replayed
the same check. Incident inserts now handle either unique conflict before reusing
the existing incident. The regression synchronizes eight workers across three
rounds of sixteen same-check calls on each database engine.

```powershell
.\scripts\postgres-integration.ps1
.\scripts\incidents-smoke.ps1
.\scripts\storage-smoke.ps1
```

The new smoke uses **actual Uvicorn HTTP and real Chromium** with intercepted
synthetic booking traffic, provider fixtures and scripted model responses. It
migrates a new scratch SQLite file, executes repeat investigations/direct checks,
stops/restarts the backend, and verifies identical history/incident records.

| Verified result | Count |
| --- | ---: |
| Persisted check observations after restart/repeat checks | 15 |
| Synthetic OPEN incidents | 3 |
| Linked unhealthy observations | 7 |
| Persisted supported assessments/recommendations | 3 |
| n8n workflow observations of execution 1001 | 4 |
| Vercel deployment observations | 2 |
| Browser failure observations | 1 |
| Duplicate incidents | 0 |

Healthy and missing-execution checks create no new incident; a healthy result
does not resolve the prior incident. Model findings remain scoped and unverified
as real customer causes. The older storage smoke also passed with incidents
explicitly disabled: 9 checks, 8 services, identical IDs after restart, 0 incidents.

Ignored evidence/log files are under `work/evidence/phase-10-*` and
`work/logs/phase-10-postgresql-tests.log`. The unchanged harness retains legacy
Phase 7 output filenames; this phase copies final evidence to Phase 10 names.
The isolated PostgreSQL server is stopped after verification. No Windows service
is installed and no cloud/customer database is accessed.

The local development database was backed up using SQLite's backup API and
explicitly upgraded from 0001 through 0002 to 0003, with a backup before each
step. Backup integrity, final integrity, foreign keys and all original column values were verified. It contained 0 services,
0 checks and 0 incidents before migration. Its backup remains on D: under
`work/backups/phase-10-before-upgrade-*.sqlite3`. The ignored `.env` is unchanged;
automatic incident detection remains off there until explicitly enabled.

Live Nemotron inference/tool calling, n8n, Vercel, Supabase and cloud/monitored
PostgreSQL remain unverified. Synthetic evidence is not live provider validation.
No remote, push, deployment, license change or provider write was added.

## Next phase

**Phase 10 is complete. Next: Phase 11 — the first approved write (bounded n8n
retry).** Five phases remain: 11 approved remediation, 12 recovery verification,
13 frontend, 14 deployment/access controls, 15 demo. Do not begin Phase 11 without
the user's next phase instruction.

## Primary implementation references

- [Alembic batch migrations](https://alembic.sqlalchemy.org/en/latest/batch.html)
- [SQLAlchemy SQLite transactions](https://docs.sqlalchemy.org/en/20/dialects/sqlite.html)
- [PostgreSQL partial indexes](https://www.postgresql.org/docs/current/indexes-partial.html)
- [PostgreSQL constraints](https://www.postgresql.org/docs/current/ddl-constraints.html)
- [SQLite partial indexes](https://www.sqlite.org/partialindex.html)
