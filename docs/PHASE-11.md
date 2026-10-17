# Phase 11 — First approved write: bounded n8n execution retry

Implemented and locally verified on 17 October 2026. Stop after this phase; recovery verification is Phase 12.

## What changed

The backend now implements `retry_n8n_execution(execution_id)` behind a separate
operator action service. It is **not** an AI tool or an HTTP execution endpoint.
The existing model registry still contains 13 read/observation tools. Operator
approval and execution use a local CLI; HTTP exposes only policy and audit reads.

Defaults:

```dotenv
N8N_RETRY_MODE=disabled
N8N_RETRY_WORKFLOW_IDS=[]
```

Enablement requires migrated application storage, a nonempty allowlist of at
most 25 unique workflow IDs, matching n8n monitoring/retry modes, and a local
development/test environment. Live mode also requires existing HTTPS n8n API
configuration and credentials. Production enablement is rejected pending access
controls. Existing provider settings and the ignored `.env` are unchanged.

## Policy and approval boundary

An action proposal must reference a stored unhealthy n8n execution check already
linked to the specified unresolved incident. Its normalized evidence must say
`error` with present data. Check kind, workflow ID, service identity, source
fingerprint and synthetic/live mode must match. The workflow must be allowlisted.
The stored observation must have been captured within five minutes.

Planning does not contact n8n or execute an action. It creates/reuses a PENDING
record containing the exact execution/workflow, linked check/incident, target
fingerprint, mode, expiry and a warning that retry may duplicate external effects.
The approval window is at most five minutes from observation capture. Repeating
a proposal never resets the window or creates a fresh retry opportunity.

The operator must inspect the proposal and explicitly acknowledge replay risk
for its exact action ID using `--approve-retry-side-effects`. Approval is a local
operator assertion, not authenticated human identity or a guarantee that the
workflow is idempotent. Local OS/database access is the trust boundary. This is
not a production authorization system or a tamper-proof audit against a database
owner. Network/API approval can be introduced only with appropriate access controls.

The approved action is atomically claimed before provider I/O. A uniqueness
constraint allows one action per configured source fingerprint and original
execution in the shared application database. Atomic conditional updates allow
one claim and one dispatch-intent transition. Competing CLI processes cannot
claim the same action twice. One action runs at a time per service instance.

Before dispatch, a fresh provider read must still show the same execution and
workflow in error, with present data, no retry ancestor and no recorded successful
retry. Missing/malformed/changed metadata fails closed. Dispatch intent commits
before the POST; expiry is checked again at that point. An unavailable audit
database prevents dispatch. The CLI never accepts an arbitrary URL, SQL, workflow
body, credential, load-workflow option or free-form action type.

## n8n contract and outcome

The adapter sends exactly one bounded POST attempt to the configured public
HTTPS API root at `executions/{executionId}/retry`, with `{"loadWorkflow":false}`.
This chooses the workflow saved with the original execution. The provider
controls retry behavior; this is not a promise that earlier side effects cannot
repeat. Official documentation describes both workflow-selection behavior and
the new execution receipt. [n8n execution API](https://docs.n8n.io/connect/n8n-api/executions/)

The adapter shares the existing destination validation, DNS pinning, TLS,
no-proxy/no-redirect/no-transport-retry policy and 1 MiB response cap. Provider
calls each use the configured deadline (at most 30 seconds). There is no retry
loop, queue, bulk action or workflow mutation. Private/loopback provider targets
remain blocked by the existing network policy.

Only normalized new execution ID, original execution ID, workflow ID, retry mode
and provider execution state are retained from the receipt. Unexpected identities,
malformed JSON, duplicate keys, oversized responses and secret echoes fail closed.
Provider payloads, run data, customer data and error bodies are not saved/printed.

| Audit state | Meaning |
| --- | --- |
| PENDING | Proposal exists; no approval consumed and no provider I/O |
| EXECUTING | Approval consumed; may include an abandoned/crashed intent |
| ACCEPTED | A matching new-execution receipt was validated and saved |
| REJECTED | Preflight failed before a POST was attempted |
| UNKNOWN | Dispatch intent exists but the provider outcome was not established |

An accepted receipt is not successful remediation or recovery. Even a provider
`success` state alone would not verify the business flow. This phase leaves the
incident OPEN/INVESTIGATING, with recovery/business-outcome flags false. The
fixture receipt deliberately reports a new execution in `running` state.

Timeouts, transport errors, 4xx/5xx responses or invalid receipts after dispatch
are conservatively UNKNOWN, with no automatic resubmission. If recording the
final outcome fails, the consumed EXECUTING intent remains blocked and the CLI
reports an uncertain, non-durable outcome. A validated new execution ID is still
returned if one was received. A crash between intent commit and POST can consume
an action without sending it. Such ambiguity requires manual reconciliation;
there is no reset/retry API in this phase.

The application does not guarantee exactly-once side effects at n8n. External
operators/clients may retry concurrently, and provider metadata cannot prove no
other retry is in flight. Workflow-specific replay safety and review remain
necessary. The safeguard here is one dispatch attempt from this application's
durable action record, not global control over the external system.

Cancellation keeps active workers tracked and drains them before engine disposal.
Shutdown before dispatch can reject an approved intent. Once dispatch is in
progress it cannot be revoked; its receipt/uncertainty is saved and replay stays
blocked across restart. No incident is automatically resolved.

## Operator commands and read API

Run the repeatable isolated demonstration:

```powershell
.\scripts\retry-smoke.ps1
```

It uses a fresh scratch SQLite file, actual Uvicorn/CLI processes and an in-memory
synthetic n8n transport. It does not contact a live n8n instance or send a message,
booking, payment or other real workflow side effect.

For interactive fixture use, set session variables before explicit migration and
backend startup:

```powershell
$env:STORAGE_MODE = 'local'
$env:N8N_MODE = 'fixture'
$env:INCIDENTS_ENABLED = 'true'
$env:N8N_RETRY_MODE = 'fixture'
$env:N8N_RETRY_WORKFLOW_IDS = '["wf-booking"]'
.\scripts\migrate.ps1 -Action upgrade
.\scripts\run.ps1
```

Capture execution 1001 through the backend to obtain a linked check/incident.
Then use their actual UUIDs to create and inspect a concrete proposal. From the
repository root in an operator terminal, with the same environment configuration:

```powershell
. .\scripts\environment.ps1
Push-Location backend
& $ProjectPython -m app.actions.cli plan --incident-id $incidentId --check-id $checkId
& $ProjectPython -m app.actions.cli inspect --action-id $actionId
& $ProjectPython -m app.actions.cli execute --action-id $actionId --approve-retry-side-effects
Pop-Location
```

`$incidentId`, `$checkId` and `$actionId` refer to the reviewed stored UUIDs, not
arbitrary provider targets. Omitting the approval flag makes no provider call.
Changing the source/mode or removing the workflow from the allowlist prevents
approval of an older proposal. Live mode is separately opt-in; the build and
verification of this phase performed no live provider write.

Local read-only HTTP routes:

- GET /actions: configured action policy and approval requirements.
- GET /history/actions: bounded audit list (1–100 rows, offset 0–10000).
- GET /history/actions/{UUID}: one proposal/approval/dispatch/receipt record.

These routes are hidden in production. There is no HTTP create, approve, execute,
reset or resolve endpoint. The AI cannot call the CLI or the action service through
its tool registry. Investigation remediation flags remain false because that
controller still performs read/observation tools only.

## Storage and migration

New explicit Alembic head: `0004_approved_n8n_retry`. It adds only `retry_actions`
to application storage, including evidence foreign key, deduplication constraint,
approval/dispatch/completion times, receipt metadata and state consistency guards.
It does not alter provider/customer databases or auto-migrate at startup.

Migration tests downgrade/re-upgrade populated prior check/incident history and
verify preservation on SQLite and PostgreSQL. Downgrade drops action audit data
and is used only on disposable test databases. Back up before any schema change.

The existing local development database was backed up using SQLite's backup API
and explicitly upgraded from 0003 to 0004 after scratch verification. Backup/
database integrity, foreign keys and all prior column values passed verification.
Its five existing data tables were empty and no retry action was created there.
The backup remains under `work/backups/phase-11-before-upgrade-*.sqlite3` on D:.
Provider `.env` settings are unchanged; retry remains disabled there.

## Verification

Final regression: **819 passed, no skips**, in **161.50 seconds**, including
**99 new Phase 11 cases**, all **98 isolated PostgreSQL variants**, SQLite and six
real Chromium cases. Ruff lint/format passed for **97 Python files**; pip reports
no broken requirements. No dependency changes were needed.

Coverage includes exact pinned API method/path/payload, unsafe destinations,
approval omission, scope/identity changes, expiry before claim and dispatch,
concurrent proposals/claims, repeated execution, real CLI/server restart,
invalid receipts, uncertain POSTs, audit failure before/after dispatch,
database state guards, migration preservation, cancellation draining, production
rejection, and unchanged read-only model tools.

The initial 720-case baseline rerun had one timing-sensitive storage-timeout test
failure: a 20 ms test deadline expired before its fixture reached storage. That
test now allows one second for the real fixture adapter while an event keeps
storage blocked until after the expected timeout. Product deadlines are unchanged.

Actual operator/HTTP smoke passed: one accepted synthetic action, one durable audit
record, missing approval blocked, repeat execution blocked before/after backend
restart, new execution 2001 in running state, incident still OPEN. No model write
tool or HTTP execution route exists. Evidence/logs are saved under ignored
`work/evidence/phase-11-*` and `work/logs/phase-11-postgresql-tests.log`.

No new dependency, Windows service, Git remote, push, deployment, provider setting
change or live provider write was introduced. Live n8n retry behavior and all
previously unverified live integrations remain unverified.

## Next phase

**Phase 11 is complete.** Next: **Phase 12 — verify recovery before incident resolution**. Four phases
remain after this milestone: 12 recovery verification, 13 frontend, 14 deployment
and access controls, 15 demo. Stop after Phase 11.
