# Phase 9 — Bounded AI investigation loop

Implemented and locally verified on 17 October 2026. Stop after this phase.

## Implemented

The backend can now run the model/tool/evidence cycle through `NebiusClient`
and the Phase 8 registry. A turn can select tools, inspect their normalized
results, select further tools, and finish with an evidence-linked conclusion.
The loop does not create incidents or execute remediation.

New local routes:

- `GET /agent`: configured mode/source and execution limits, not connectivity.
- `POST /investigations`: one bounded investigation, including its evidence trail.

New setting: `INVESTIGATION_MODE=disabled|fixture|live`, default **disabled**.
No existing ignored configuration, provider key or development database was
changed. There are no new dependencies or database migrations.

## Local fixture run

```powershell
.\scripts\agent-smoke.ps1
```

This starts actual Uvicorn and uses a **scripted model response fixture** through
the same HTTPX request serialization/parser and orchestration path as live mode.
It is not a real Nemotron response or evidence of AI reasoning quality. n8n and
infrastructure providers are also fixtures. No provider network call is made by
this smoke command.

The single supported fixture question is:

```json
{"question":"Why are booking confirmations missing?"}
```

The fixture selects failed executions, execution 1001, Supabase service health,
and the fixed PostgreSQL probe. It completes **3 model turns and 4 tool calls**,
then cites execution evidence `e2` for the recorded HTTP 401 rejection. Supabase/
PostgreSQL healthy fixtures do not prove those systems are unrelated to a real
customer failure. The scripted sequence is fixed; another question is rejected.

For interactive use, set the three modes in the current PowerShell session:

```powershell
$env:INVESTIGATION_MODE = 'fixture'
$env:N8N_MODE = 'fixture'
$env:INFRASTRUCTURE_MODE = 'fixture'
.\scripts\run.ps1
```

Then, from another terminal:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/investigations -ContentType 'application/json' -Body '{"question":"Why are booking confirmations missing?"}'
```

Fixture investigation mode requires fixture n8n/infrastructure modes and excludes
the live website HTTP/DNS/TLS tools from its catalog. It is rejected in production.
The same controller uses all 13 registered tools in opt-in live inference mode.

## Live path and provider boundary

`INVESTIGATION_MODE=live` uses the existing ignored `NEBIUS_API_KEY` and configured
`NEBIUS_MODEL`. The question and restricted tool evidence are sent to Nebius;
live completion requests can consume provider credits. Monitoring adapter modes
remain independently operator controlled; live inference may inspect synthetic,
non-synthetic or mixed observations, explicitly labeled in the report.

Each investigation first checks the configured model with `GET /v1/models`, then
uses `POST /v1/chat/completions` with `messages`, registry `tools`, `tool_choice:
auto`, bounded `max_tokens`, `stream: false` and `store: false`. Tool-result
messages carry matching call IDs. Multiple calls are executed sequentially.
No automatic retry or model fallback exists. Provider errors/refusals, mismatched
models, duplicate/malformed payloads and incomplete/truncated output fail closed.

The existing model ID was preserved. An unauthenticated public catalog request
returned 401, so current model availability/capabilities were not established.
Authenticated live model selection, tool calling and JSON conclusion behavior
remain **unverified**. Live runs check availability before sending the question;
catalog presence alone does not prove tool-calling capability or hackathon eligibility.

## Bounds and cancellation

| Boundary | Limit |
| --- | --- |
| Request body / question | 4 KiB JSON / 2,000 characters and 3,000 UTF-8 bytes |
| Catalog requests | One GET per investigation |
| Completion attempts | At most 6; configured token cap per attempt |
| Tool calls | At most 8; at most 4 per model turn |
| Concurrency | One investigation and one registry operation per instance |
| Investigation response deadline, after question validation | 120 seconds |
| Retained evidence | 128 KiB budget, reserving space before starting another tool |
| Model context / serialized request | 192 KiB / 256 KiB |
| Provider response / final JSON draft | 1 MiB / 8 KiB |

Extra request fields, duplicate JSON keys and invalid types are rejected without
echoing input. Unknown/disallowed tools and duplicate call IDs are checked across
a model batch before dispatch. Registry argument validation remains per call.
Repeated canonical JSON calls stop the run; semantically equivalent different
arguments are still bounded by the total call limit. There is no queue or
automatic pagination. Known configured secret echoes are rejected.

Deadline/task cancellation stops future model requests and cancels the model
loop. Its owner continues draining any registry worker/history transaction and
holds the investigation slot until actual completion. Shutdown drains controller,
registry and history in that order. Cleanup can outlive the response deadline.
HTTP client disconnection is not actively monitored; the overall deadline still
caps the investigation. These are cooperative adapter boundaries, not an OS
sandbox for arbitrary plugins or a global quota across multiple server processes.

## Evidence and conclusions

The model must return a strict JSON draft containing a hypothesis code, actual
evidence IDs and recommended next-step codes. The server validates citations and
checks the selected hypothesis against those observations. It computes the
assessment and provenance itself and renders a fixed, scoped summary. Free-form
model prose and private reasoning are not returned or used as verified facts.
No provider-enforced structured-output guarantee is assumed.

Supported hypothesis categories are authentication/permission rejection, rate
limiting, upstream HTTP error, workflow failure, website/browser failure,
deployment failure, infrastructure failure, and unknown. This finite vocabulary
is deliberate; arbitrary novel root-cause narratives are outside this phase.
Matching evidence supports an observed issue, not proof it caused the user's
reported problem. HTTP 401 cannot establish an expired/revoked credential.

Reports separate `COMPLETED`, `INCOMPLETE`, `CHECK_FAILED` and `REJECTED` from
operational assessment. COMPLETED means a validated conclusion was produced;
it does not mean a service recovered. `no_failure_observed` applies only to the
sampled observations and is not an all-clear. UNKNOWN/CHECK_FAILED never become
an unhealthy service diagnosis. Inference source and evidence provenance are
separate fields; `model` identifies the configured model, including in fixtures.

Every report keeps `root_cause_verified`, `business_outcome_verified`,
`incident_created` and `remediation_executed` false. Collected results survive
provider errors, invalid conclusions, budgets/deadlines and storage failures.
A timed-out in-progress tool may finish/save later without appearing in the
returned evidence trail; its slot stays occupied until completion.

Check history is captured by the registry, not a new model-controlled storage
tool. List pages are not health observations. Investigations themselves are not
persisted as new database records; incident management remains Phase 10 onward.
Production routes and internal investigation execution remain disabled pending
authentication/deployment controls.

## Verification

Baseline: **511 tests passed, no skips**, using the unchanged isolated PostgreSQL
harness in the current execution environment. This successfully reran the 25
PostgreSQL variants that were skipped in Phase 8.

Final regression: **608 tests passed, no skips**, in 43.21 seconds. Ruff lint and
format checks passed for 78 Python files; pip found no broken requirements.
The run includes **97 new Phase 9 cases** covering model wire format,
all conclusion categories, actual six-turn/eight-call limits, invalid schemas,
unsupported claims/citations, injection/write attempts, fixture/live separation,
secret filtering, provider errors, preserved partial evidence, real SQLite
history/missing migrations, cancellation, worker draining and production rejection.
Existing text-response bounds remain compatible.

Actual Uvicorn fixture smoke passed with 3 model turns, 4 tool calls, synthetic-only
evidence and no incident/remediation. SQLite integration tests saved 3 health
observations across 3 services without creating an incident. The existing six
Chromium tests and real isolated PostgreSQL variants run in the full regression.

Commands:

```powershell
.\scripts\postgres-integration.ps1
.\scripts\agent-smoke.ps1
```

Evidence: `work/evidence/phase-9-investigation-smoke.json`,
`work/evidence/phase-9-postgresql.json`, and
`work/logs/phase-9-postgresql-tests.log`. The harness's legacy Phase 7 filenames
are copied to phase-specific names for this milestone. All scratch data stays
on D:. No running test server or Windows database service is retained.

## Official references checked

- [Nebius function calling and tools](https://docs.tokenfactory.nebius.com/ai-models-inference/function-calling)
- [Nebius chat completion API](https://docs.tokenfactory.nebius.com/api-reference/inference/create-chat-completion)
- [Nebius structured output](https://docs.tokenfactory.nebius.com/ai-models-inference/json)

## Next

**Phase 9 is complete. Next: Phase 10 — autonomous incident creation**, based on
verified observations and existing database constraints. Approved remediation,
recovery verification, frontend and deployment remain later phases. No live AI
or provider integration is claimed verified; no GitHub remote/push or deployment
was added. Stop at this milestone.
