# Phase 8 — Strict AI tool registry

Completed and locally verified on 17 October 2026. Stop after this phase.

## Implemented

An internal `ToolRegistry` exports function descriptors, validates every call,
dispatches only fixed monitoring handlers, projects normalized evidence, and
records health observations through the existing history service. No new
dependencies, provider operations, migrations or configuration settings were added.

`GET /tools` exposes the catalog/policy in development/test. There is no public
tool-execution endpoint. Both catalog and internal execution are disabled in
production pending deployment access controls.

| Tool | Accepted arguments | Response deadline |
| --- | --- | --- |
| `list_website_targets` | Empty object | 5 seconds |
| `check_website_http` | Registered `target_id` | 12 seconds |
| `check_dns` | Registered `target_id` | 12 seconds |
| `check_ssl` | Registered `target_id` | 12 seconds |
| `test_website_flow` | Fixed synthetic `flow_id` | 41 seconds |
| `list_n8n_workflows` | Optional `limit`, `cursor` | 31 seconds |
| `list_failed_n8n_executions` | Optional `limit`, `cursor`, `workflow_id` | 31 seconds |
| `get_n8n_execution` | Validated `execution_id` | 31 seconds |
| `check_vercel_deployment` | Empty object; configured deployment | 41 seconds |
| `get_vercel_deployment_events` | Empty object; at most 25 build events | 41 seconds |
| `check_supabase_project` | Empty object; configured project | 41 seconds |
| `check_supabase_health` | Empty object; configured db/auth/rest | 41 seconds |
| `check_postgres` | Empty object; configured fixed read-only query | 41 seconds |

The existing HTTP tool covers both website and endpoint targets. Read/observation
tools cannot write to monitored systems. Synthetic browser form submissions are
locally intercepted; application history is an explicit local persistence effect.

## Validation and execution

- Input must be a JSON object encoded as a string, at most 4,096 UTF-8 bytes.
  Duplicate keys, non-finite constants, malformed/deep JSON, unknown properties,
  invalid IDs and unregistered targets are rejected before adapter I/O.
- Strict Pydantic validation rejects `true`, `1.0`, or `"5"` as integer page
  limits. Limits are 1–50; cursors are at most 2,048 characters.
- Function schemas set `additionalProperties: false`; registered website IDs
  also appear as an enum. Server validation is authoritative. Provider-enforced
  strict decoding and live model/schema compatibility have not been verified.
- One in-flight registry call per backend instance; no queue, automatic retry
  or pagination. Overlapping calls return `busy` immediately.
- Response deadlines/caller cancellation do not cancel underlying adapter work.
  The slot stays occupied until the adapter and history operation actually
  finish. Cancelling a thread await would not stop its process/transaction.
  Existing adapter network, deadline and process-cleanup bounds remain in force.
- Shutdown drains registry work before closing history. This boundary supports
  the existing bounded adapters; it is not an OS sandbox for arbitrary plugins
  or a global multi-process quota.

## Result contract

`ToolResult` has `name`, `status`, `reason`, `data`, and `history`.
Dispatch status is `OK`, `REJECTED`, or `EXECUTION_FAILED`. **OK means dispatch
completed, not that a service is healthy.** Health and inspection state remain
inside `data`. UNKNOWN/CHECK_FAILED never become UNHEALTHY.

Health observations include service/component/type/status, nullable healthy and
severity/latency fields, timestamp, synthetic flag, restricted evidence and false
root-cause/business-outcome verification flags. n8n list pages retain normalized
metadata/next cursor and are not persisted as health observations. HTTP 401 does
not establish that a credential expired or was revoked.

Free-text summaries, raw provider bodies/logs and connection strings are not
forwarded. Configured secret echoes are rejected, including JSON-escaped strings.
This is not a general guarantee that all provider metadata is non-confidential.
Retained evidence must be treated as untrusted data, never as instructions.

Output is capped at 65,536 bytes in canonical
`result.model_dump_json().encode("utf-8")` form, including history metadata.
Oversized evidence fails closed rather than being silently truncated.

History status is `saved`, `disabled`, `unavailable`, or `not_applicable`.
Saved history includes a validated check UUID. API and tool observations share
the same identities. Storage errors preserve operational observations. If storage
is pending at the response deadline, the observation returns with `unavailable`;
the transaction may later complete while the slot remains occupied. A timeout
does not prove that no history was saved.

Usage for a future orchestrator on the application's event loop:

```python
definitions = app.state.tool_registry.definitions()
result = await app.state.tool_registry.execute(
    "get_n8n_execution", '{"execution_id":"1001"}'
)
content = result.model_dump_json()
```

This performs no model request or autonomous investigation.

## Verification

- Unchanged baseline: **413 passed, 25 skipped**, lint/format passed.
- Final full ordinary run: **486 passed, 25 skipped**, including **73 new Phase 8
  cases** and the existing six real Chromium tests. Ruff lint passed; all 69
  checked Python files were formatted. Pip reported no broken requirements.
- Cases cover strict schemas/arguments, all 13 dispatch paths, single-page
  forwarding, fixture semantics, restricted evidence, byte budgets, secret
  echoes/escaping, invalid latency, shared identities, missing migrations,
  storage errors, timeout/cancellation slot retention, shutdown and production.
- Registry smoke: 13 cataloged tools; 12 calls covering 10 distinct tools,
  including both real Chromium fixture flows. **9 saved checks across 8 services**
  in a fresh explicitly migrated SQLite scratch database; **zero incidents**.
  Website dispatch uses injected local test adapters in the automated suite.
- Actual Uvicorn HTTP smoke passed for health, docs/OpenAPI, the 13-tool catalog,
  absent public execution route, and existing invalid-target rejection.

The Phase 8 PostgreSQL harness rerun timed out during `initdb`, before a test
server started. A diagnostic with smaller memory settings also stalled; its cause
is not established. Phase 7's successful 438-test PostgreSQL/SQLite run remains
historical evidence, not a new Phase 8 verification. The final ordinary runner
explicitly skipped its 25 PostgreSQL variants. No cloud database was accessed.

```powershell
.\scripts\test.ps1
.\scripts\tools-smoke.ps1
.\scripts\postgres-integration.ps1
```

Smoke evidence: `work/evidence/phase-8-tools-smoke.json`. Scratch databases,
browser files, diagnostics and logs stay in ignored `work/` on D:. Existing
ignored `.env` and development history database were not modified.

## Official references checked

- [Nebius function calling and tools](https://docs.tokenfactory.nebius.com/ai-models-inference/function-calling)
- [Pydantic strict validation](https://docs.pydantic.dev/latest/concepts/strict_mode/)
- [Python asyncio shielding/timeouts](https://docs.python.org/3.12/library/asyncio-task.html)
- [PostgreSQL initdb options](https://www.postgresql.org/docs/18/app-initdb.html)

## Limits and next phase

No Nebius request, AI reasoning loop, automatic incident creation, remediation,
recovery resolution, frontend, deployment or GitHub push was added. Provider
data in the registry smoke is synthetic. Live Nebius/Nemotron, n8n, Vercel,
Supabase and monitored PostgreSQL connections remain unverified.

Next: **Phase 9 — the actual bounded AI investigation loop**, using this registry
with explicitly separated fixture/live validation. Phase 8 is the tool boundary,
not a complete autonomous agent.
