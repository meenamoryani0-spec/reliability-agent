# Current implementation state

Updated 17 October 2026 after Phase 9.

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
- Phase 7: SQLAlchemy models, Alembic migration 0001_history, transactional
  repository/service layer, history reads and capture of executed check results.
- Phase 8: strict registry of 13 existing monitoring tools, generated function
  schemas, bounded internal dispatch, normalized evidence and history capture.
  Local GET /tools catalog; no public execution endpoint. Production access is disabled.
- Phase 9: bounded model/tool investigation loop, local GET /agent and POST
  /investigations, validated evidence-linked conclusions, explicitly labeled
  scripted model fixtures and an opt-in live Nebius path. Disabled by default.

Final Phase 9 regression: **608 passed, no skips**, including **97 new Phase 9
cases**, all 25 isolated PostgreSQL variants and six real Chromium cases.
Ruff lint/format and pip checks pass; 78 checked Python files are formatted.
Actual Uvicorn investigation smoke passed with 3 scripted model turns and 4
registry tools. It returned a cited authentication-rejection finding with
synthetic-only evidence, no verified root cause/delivery, and no incident/action.
SQLite API tests persisted 3 observations across 3 services without incidents.

Phase 8 had **486 passed, 25 skipped** and 73 registry tests. Its registry smoke completed 12
calls covering 10 distinct tools, saved 9 observations across 8 services to fresh
SQLite history, and created zero incidents. Uvicorn HTTP catalog smoke passed.
Website dispatch is covered by injected local test adapters.

Phase 7 previously passed all **438 tests**, including real isolated PostgreSQL,
SQLite and Chromium. The Phase 8 PostgreSQL harness rerun timed out during initdb,
before server startup. A smaller-memory diagnostic also stalled; cause unverified.
The ordinary runner explicitly skips those 25 PostgreSQL cases. Phase 9's unchanged
harness subsequently passed all 511 baseline tests and all 608 final tests in the
current execution environment. The earlier initialization failure's cause is not
established. No test PostgreSQL server was left running or cloud database accessed.

The Phase 7 backend storage smoke saved 9 observations across 8 services, stopped
and restarted Uvicorn, and recovered identical IDs. No incident was automatically
created. Incident storage supports OPEN/INVESTIGATING; RESOLVED is rejected until
a later migration and verified recovery workflow exist.

Local history is enabled/migrated in the ignored development .env, using
work/data/reliability.sqlite3 on D:. Startup never applies migrations. Application
storage is distinct from monitored POSTGRES_* credentials. Remote application
PostgreSQL uses its own reliability schema; cloud access has not been tested.

SQLAlchemy 2.0.55 and Alembic 1.20.0 are locked. Portable EDB PostgreSQL 18.6
binaries are under ignored work/postgres-runtime/. In Phase 7 a scratch loopback-only
cluster/database exercised migrations, rollback, constraints, concurrency and
repository reopen. The server was stopped; no Windows service was installed.
No cloud/customer database was accessed.

The Phase 6 monitored PostgreSQL probe still uses driver fixtures; Phase 7
separately verifies application storage on a real local PostgreSQL server.
Live Nebius, n8n, Vercel, Supabase and cloud PostgreSQL remain unverified.
Synthetic evidence never establishes a real customer root cause or outcome.

The original test stall was isolated to Windows asyncio socket-pair creation
under network restrictions. The unchanged baseline passed after network access
was granted; no event-loop bypass was introduced.

All new dependencies, binaries, databases, caches, temporary files, logs and
verification evidence stay on D:. No GitHub remote, push, license selection or
deployment was added. History routes remain disabled in production until
access controls exist. Database files/environment configuration are ignored.

Registry calls accept at most 4 KiB of arguments and return at most 64 KiB of
canonical UTF-8 JSON. One in-flight call per instance, no queue/retries/pagination.
Timeout/cancellation retains the slot until the bounded adapter actually finishes.
Storage failures preserve observations and report unavailable history. Existing
.env, development history, dependencies and migrations were unchanged in Phase 8.

Phase 9 permits 6 completion attempts, 8 tool calls, a 120-second investigation
response deadline and one investigation in flight. Task cancellation stops model
work while the owner drains registry workers/history before releasing its slot.
Conclusions use a finite vocabulary and require valid supporting evidence IDs;
raw model prose/reasoning is not returned as fact. Root cause, business outcome,
incident creation and remediation flags remain false. Fixture inference is a
scripted protocol test, not verified Nemotron reasoning. Live availability/tool
calling remains unverified; unauthenticated catalog access returned 401.
Existing ignored .env/provider settings and development history were untouched;
no new dependencies or migrations were added. Production investigation is disabled.

**Phase 9 is complete. Next: Phase 10 — autonomous incident creation.**
Six phases remain (10–15): automatic incidents, first approved write, recovery
verification, frontend, deployment and demo.

Read docs/PHASE-9.md before continuing. Keep using local fixtures where provider
credentials are unavailable; do not rebuild completed phases.
