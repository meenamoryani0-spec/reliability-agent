# Phase 7 — Application database persistence

Completed and locally verified on 17 October 2026. Stop after this phase.

## Implemented

SQLAlchemy models, explicit Alembic migration `0001_history`, a transactional
repository/service layer, check-result capture and bounded history reads for:

- Monitored services: stable identity, category, component, synthetic flag, timestamp.
- Checks: service reference, kind/status, UTC timestamps and projected normalized evidence.
- Incidents: same-service detection reference, unresolved status, severity and timestamp.

PostgreSQL uses a separate `reliability` schema; local SQLite uses a file confined
to project work/. Application database credentials are separate from monitored
`POSTGRES_*` settings. Startup and HTTP routes never apply migrations.

No autonomous incident creation was added. The internal repository can store an
OPEN incident tied to an unhealthy check. Foreign keys prevent cross-service
references and a unique constraint prevents duplicate records for the same check.
Only OPEN/INVESTIGATING are permitted; RESOLVED requires a later migration and
verified recovery workflow. No public incident-write or arbitrary SQL endpoint exists.

## Verification

- Unchanged Phase 6 baseline: **360 tests passed**, lint/format passed.
- Final complete run: **438 tests passed**, including **78 new Phase 7 cases**.
  All 25 PostgreSQL variants, 25 SQLite variants, 28 API/configuration cases and
  the existing six real Chromium tests executed. **No skips** in the final run.
- Ruff lint/format passed; pip check found no broken requirements.
- Actual backend restart smoke: **9 saved checks across 8 services**, identical
  stored check IDs after stopping/restarting Uvicorn, zero automatic incidents.
- Upgrade is repeatable; downgrade/upgrade was exercised only on disposable
  test databases. Records and incidents survive recreating the engine.
- Tests cover rollback, concurrent first registration, foreign keys, invalid
  states, incident evidence links, no resolution, UTC timestamps, pagination,
  target/synthetic separation, bounded evidence, source/credential omission,
  missing migrations, unchanged check bodies and production route rejection.

The HTTP smoke uses actual SQLite/Uvicorn/Chromium with synthetic external
provider data. The PostgreSQL run uses a **real PostgreSQL 18.6 server**, not a
driver mock. The harness creates a random loopback-only scratch cluster/database,
runs the full test script, then stops it. No matching test PostgreSQL process
remained afterward. No Windows service was installed or cloud database accessed.

SQLAlchemy **2.0.55** and Alembic **1.20.0** are installed with hashed locks.
Official EDB binaries, archive, disposable clusters, logs and caches stay on D:.
Local history settings were added to the ignored development .env and migrated;
existing provider credential settings were preserved and not printed.

Evidence:

- `work/evidence/phase-7-storage-smoke.json`
- `work/evidence/phase-7-postgresql.json`
- `work/logs/phase-7-postgresql-tests.log`
- `work/logs/storage-before-restart.log` and `storage-after-restart.log`

## Runtime behavior

New checkouts default to disabled storage. This computer has local history
enabled at `work/data/reliability.sqlite3`. Run `scripts/migrate.ps1 -Action status`
to inspect revision and `-Action upgrade` to explicitly apply migrations.

Executed website/browser/infrastructure checks and n8n execution details are
recorded. n8n list pages are not treated as health observations. The original
check result body is unchanged. `X-History-Status` reports saved/disabled/unavailable;
successful writes also return `X-Check-Id`. Database failure does not change the
operational check status or backend liveness. History reads fail with sanitized
503 errors when storage is disabled, unavailable or requires migration.

Read routes: GET `/storage`, `/history/services`, `/history/checks`,
`/history/checks/{uuid}`, and `/history/incidents`. Pagination is limited to
1–100 rows and offset 0–10000. Each repository operation owns its transaction
and session. Reads join service metadata without one query per record.

Service identity includes component, target fingerprint and synthetic flag.
Changed targets and fixture/live observations do not share service records.
Only projected normalized evidence is stored, at most 64 KiB per check.
Raw provider payloads, free-text summaries/logs, raw build-event text and source
connection strings are omitted. UUIDs/hashes are not anonymity guarantees.

Remote PostgreSQL storage URLs must use postgresql+psycopg without arbitrary
query/DSN options. Remote TLS is forced to verify-full with Certifi. Loopback/
plaintext requires explicit development/test opt-in and is rejected in production,
as is SQLite. History routes are disabled in production pending access controls.
No HTTP migration, SQL, deletion or incident-write endpoint exists.

## Run

```powershell
.\scripts\migrate.ps1 -Action status
.\scripts\run.ps1
.\scripts\storage-smoke.ps1
.\scripts\postgres-integration.ps1
```

The PostgreSQL harness uses portable binaries under ignored work/postgres-runtime/.
Other machines can pass `-BinDir` after placing official binaries inside work/.
Without the harness, scripts/test.ps1 explicitly skips PostgreSQL variants;
the final verified full run used the harness and executed all 438 cases.

## Official references checked

- [SQLAlchemy sessions/transactions](https://docs.sqlalchemy.org/en/20/orm/session_basics.html)
- [SQLite transaction behavior](https://docs.sqlalchemy.org/en/20/dialects/sqlite.html)
- [PostgreSQL/Psycopg dialect](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html)
- [Alembic migrations](https://alembic.sqlalchemy.org/en/latest/tutorial.html)
- [PostgreSQL Windows downloads](https://www.postgresql.org/download/windows/)
- [EDB portable binaries](https://www.enterprisedb.com/download-postgresql-binaries)

PostgreSQL remains the target; SQLite supports credential-free local runs. Both
engines were actually tested rather than assumed equivalent. PostgreSQL's unique
constraint backing index is correctly accepted by migration inspection. The test
launcher was fixed for Windows inherited output handles before its successful run.

## Limits and next phase

Cloud Supabase/PostgreSQL connectivity, remote TLS and production permissions
remain unverified. Live Nebius, n8n, Vercel and Supabase integrations remain
unverified. Multi-tenant authorization and retention policy remain future work.
No AI registry, agent loop, autonomous incidents, remediation, recovery workflow,
frontend, deployment or GitHub push was added.

Next: **Phase 8 — strict AI tool registry for the working checks**.
