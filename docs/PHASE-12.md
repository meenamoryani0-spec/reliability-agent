# Phase 12 - recovery verification

Verified locally on 17 October 2026. This phase adds recovery verification after
the separately approved Phase 11 retry. It does not establish live provider or
customer delivery success.

## Result and evidence

- **927 tests passed, no skips**, in 277.21 seconds: SQLite, all
  **149 isolated PostgreSQL variants**, and six real Chromium cases. This adds
  **108 cases** to Phase 11's 819. Ruff lint and format pass (108 Python
  files); pip check passes. The actual CLI/Uvicorn restart smoke passes.
- Before implementation, all 819 baseline tests passed. Lint caught two long
  lines in the newly started Phase 12 code; these were corrected. The initial
  complete Phase 12 regression passed 920 tests, then seven cases were added
  for policy changes, structured provider read failure, the detection/resolution
  race and disabled/production access. The final complete regression is above.
- Fresh test-cluster initdb timed out before tests. Its cause is unestablished.
  A new optional harness fallback validates a cleanly shut-down project test
  cluster, copies it to a new D: directory, creates a new random test database,
  establishes fresh SCRAM authentication and runs the complete suite. The
  source is never modified; the harness stops its own loopback-only copy.
  No Windows service or cloud/customer database is used. Fresh initdb remains
  an unresolved environment issue; the verified fallback permits local tests.

## Behavior

`python -m app.recovery.cli verify --action-id UUID` is the local operator entry
point. It performs one bounded read of an ACCEPTED action's exact new execution.
No retry is resent, no provider write is issued and no scheduler or automatic
polling is added. Running executions can be checked again manually. Recovery
has its own disabled/fixture/live setting; a historical accepted action can be
verified while retry itself is disabled.

Verification requires the original source/mode/synthetic identity, exact new
execution ID, matching workflow, retry mode and original lineage. It requires
terminal success, present detailed data, timezone-aware start/stop times, a
read no older than 120 seconds, completion within 300 seconds and five seconds
of permitted clock skew. Every configured required node must have explicit
success for every observed attempt, with no failures; the configured completion
node must be last. The path must cover the original failed node IDs and complete
beyond them. Top-level success, a receipt, missing statuses, redacted/oversized
or missing data, stale evidence and model prose cannot resolve.

Attempts persist VERIFIED, NOT_RECOVERED or INCONCLUSIVE with captured policy,
action/incident identity, timestamps, execution IDs, finite reason and available
check reference. Checks commit separately first. Check-save failure cannot close;
proof-save failure retains the check and reports uncertainty. Successful proof
and resolution commit atomically. A shared incident containing another failed
execution remains unresolved. Per-service locks serialize detection and closure;
the race is tested on both database engines.

The scope is **n8n_required_nodes**: successful required-node execution, not
message delivery, customer booking outcome or global service recovery. Both
business_outcome_verified and root_cause_verified remain false; root cause
remains unknown/null. Repeating verification after resolution returns the
immutable historical proof with an explicit reuse flag and makes no fresh
provider read. Re-polling the historical original failure links to its resolved
incident; a different failed execution opens a new incident. Counts remain
observations, not affected customers.

`GET /recovery` describes policy; `GET /history/verifications` and
`GET /history/verifications/{UUID}` expose bounded local reads. Incident/action
reads expose the proof ID and scope. There is no HTTP/model approval, retry,
verification or resolve write route. Production enablement/history remain
blocked pending Phase 14 access controls. Timed-out/cancelled work retains its
slot until drained; shutdown waits before engine disposal.

## Storage and configuration

Migration head is **0005_verified_recovery**. A RESOLVED incident requires a
VERIFIED same-incident proof with a same-service HEALTHY stored check, guarded
by CHECKs and composite foreign keys. Nonempty legacy action/check/incident/link
preservation and proof protection are tested on SQLite and PostgreSQL. SQLite
uses a dedicated explicit migration transaction with BEGIN IMMEDIATE, temporarily
disables incoming FKs for its batch rebuild, checks every FK before commit and
restores enforcement on every exit. Normal application enforcement stays on.
Downgrade refuses to discard any recovery audit; startup never migrates.

The actual development database was backed up and explicitly upgraded from
0004 to 0005. All six prior data tables were empty and remain unchanged; the
new verification table is empty. Backup contents, integrity and FKs passed.
Backup: `D:\CODEX MAIN\2026-10-09\g\outputs\reliability-agent\work\backups\phase-12-before-upgrade-cf1245bcc77e4c699f0cdc84a2599493.sqlite3`.

The ignored .env file is byte-for-byte unchanged against the preflight hash.
Actual retry and recovery modes remain disabled and automatic incidents remain
off. Defaults/example configuration document N8N_RECOVERY_MODE=disabled and
N8N_RECOVERY_FLOWS={}. Configure actual workflow/node IDs before a live read;
the sample IDs are synthetic. No dependencies/locks, credentials, remote,
license, deployment or unrelated system settings were changed. All new files,
logs, caches, scratch databases and backups stay on D:.

## Provider contract checked

The [official n8n execution API](https://docs.n8n.io/connect/n8n-api/executions/)
documents execution detail reads and optional data; verification reuses the
existing fixed GET with includeData=true and existing API-key/TLS/DNS limits.
The [official n8n workflow interfaces](https://github.com/n8n-io/n8n/blob/master/packages/workflow/src/interfaces.ts)
define retry lineage and optional task executionStatus. We require explicit
success conservatively; versions omitting that optional field remain
inconclusive. This contract review does not verify a deployed target version.

## Remaining work

Live Nebius/model tool calling, n8n monitoring/retry/recovery, Vercel, Supabase,
and monitored/cloud PostgreSQL remain unverified. Node evidence is insufficient
to prove customer delivery. Fresh initdb still needs environment diagnosis if
the default initialization path is required.

**Phase 12 is complete locally. Three roadmap phases remain:**

1. Phase 13: the Next.js dashboard integrating health, incidents, evidence,
   diagnosis, recommendations, approval state and verification.
2. Phase 14: deployment, authentication/access controls, CORS/security,
   production configuration, hosting and production smoke tests.
3. Phase 15: one intentional failure scenario and end-to-end demo.

Stop after the local Phase 12 commit. Do not begin Phase 13 without the user's
next instruction. Preserve the one-shot retry approval/uncertainty safeguards.

Reproduce with scripts/postgres-integration.ps1 (use -TemplateDir for the verified
project-only fallback), scripts/recovery-smoke.ps1 and the explicit migration
command. Saved evidence: work/logs/phase-12-final-tests.log and
work/evidence/phase-12-{preflight,postgresql,recovery-smoke,development-upgrade}.json.
