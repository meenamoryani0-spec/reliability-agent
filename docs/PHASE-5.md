# Phase 5 — Read-only n8n integration

Implemented and locally verified on 11 October 2026. Stop at this phase.

## What works

The adapter authenticates with an operator-configured `X-N8N-API-KEY`, lists
workflows, lists recorded error executions, fetches one execution with detailed
data, and normalizes node failures. It uses current documented public v1 GET
operations, with no n8n write methods. FastAPI exposes:

- `GET /services/n8n`: configuration mode, not a connectivity assertion.
- `GET /n8n/workflows`: IDs and active flags, one bounded page.
- `GET /n8n/executions/failed`: `error` execution metadata, optionally by workflow ID.
- `GET /n8n/executions/{execution_id}`: normalized execution and node evidence.

Modes are explicit: `disabled` by default, `fixture` without credentials, and
opt-in `live`. Missing live settings return CHECK_FAILED while `/health` remains
backend liveness. Fixture mode and local inspection are disabled in production.

## Verified evidence

`scripts/test.ps1` passed **245 tests**, including the previous 158 and 87 new
n8n tests. Ruff lint and formatting checks passed. No dependencies changed.

The new tests cover the documented authentication header, GET-only request
paths/parameters, Host/SNI preservation and IP pinning, all-address public DNS
validation, rejected redirects, response limits, deadlines, no automatic retries
or pagination, sanitized provider errors, invalid schemas/IDs/dates, checked
workflow/execution identity, missing settings, production rejection, recorded
node failures, per-attempt evidence, redacted/omitted/oversized data, unsupported
data versions, and contradictory success/global-error records.

`scripts/n8n-smoke.ps1` started a real Uvicorn process and inspected fixture n8n
data through FastAPI HTTP endpoints. It returned PASS and stopped the server.
It also verified backend health/docs and existing website rejection behavior.
The final observation was about 18:12 IST (12:42 UTC), 11 October 2026:

| Evidence | Failed execution `1001` | Successful execution `1002` |
| --- | --- | --- |
| Workflow | `wf-booking` | `wf-booking` |
| Recorded n8n state | `error` | `success` |
| Normalized execution status | UNHEALTHY | HEALTHY |
| Observed node IDs | `trigger`, `crm` | `trigger`, `crm`, `confirmation` |
| CRM error | HTTP 401, `authentication_rejected` | No recorded error |
| Root cause verified | False | False |
| Real business outcome verified | False | False |

The recorded node failure and the execution-level error appear separately as
two evidence sources for the same CRM rejection. They are not two independent
incidents. The failure fixture contains no confirmation-node run. This does not
establish whether an external message reached a real customer.

Raw fixtures contain a synthetic private-data marker in customer output,
credential metadata, parameters, and error text. Tests verify that the marker
and raw error fields do not appear in API evidence. The smoke observations are
saved to ignored `work/evidence/n8n-smoke.json`.

## Safety and interpretation

- Only GET for workflow lists, error lists, and execution details is implemented.
- Live targets require a configured public HTTPS DNS hostname/default port/API
  root. Every DNS answer is checked; the selected IP is pinned with original SNI.
  Proxies and redirects are disabled. Private self-hosted instances need a
  separately designed network policy before live use.
- One provider request per read, 1–30 second deadline (default 10), 1 MiB decoded
  body limit. Up to 50 records per page; pagination is caller-driven and partial
  pages are explicit. At most 100 nodes, 100 attempts per node, and 25 errors
  are normalized; exceeding normalization bounds fails the inspection.
- No credential retrieval, execution, retry, activation, deactivation, or
  workflow modification exists. Code restrictions do not narrow the API key's
  actual permissions; use read scopes where supported.
- IDs, states, timestamps, HTTP codes, fixed categories, cursors, and hashed node
  references are retained. Names, messages, stacks, credentials, parameters,
  inputs, and outputs are discarded. Hashes are not an anonymity guarantee.
- n8n API 401/403/429/404 or transport errors are CHECK_FAILED, not diagnoses of
  a business workflow. A successfully fetched execution may independently be
  UNHEALTHY because its saved state is `error` or `crashed`.
- A recorded node 401 supports authentication rejection. It does not distinguish
  an expired key from a revoked, missing, or incorrectly configured credential.
  A recorded 403 is `permission_denied`.
- Missing/redacted/oversized details cannot establish a node cause. The adapter
  respects provider redaction and does not request reveal or override display
  size limits. `lastNodeExecuted` alone is not treated as a failed node.
- Success is a recorded execution state, not proof a booking or confirmation
  reached its intended destination. No incidents are created or resolved here.

## Run locally

```powershell
# From the existing repository; no API credentials are required.
.\scripts\test.ps1
.\scripts\n8n-smoke.ps1
```

For normal API exploration, put `N8N_MODE=fixture` in the ignored `.env` and run
`scripts/run.ps1`. Optional live settings are documented in `.env.example` and
README.md; no real keys or instance were configured or accessed in this phase.
All new source, test data, temporary references, caches, logs, and evidence are
on D:. The existing virtual environment/dependency locks were reused.

## Documentation verification

Official authentication/pagination docs and the generated workflow/execution
OpenAPI pages were read on 11 October 2026. Their JSON specifications were
downloaded to ignored `work/reference/n8n/` and inspected for GET paths, query
parameters, response fields, and authentication. The execution detail path is
`/executions/{executionId}`; list filtering uses `status=error`, and fetching
details uses `includeData=true`. The parser validates the metadata it consumes
and ignores unused provider fields rather than copying complete payloads.

Detailed node evidence was checked against the official source interfaces:
`data.resultData.runData` maps node names to task attempts; each attempt can hold
`error` or `redactedError`. Execution-level errors and `lastNodeExecuted` are
separate fields. `NodeApiError.httpCode` supplies the recorded status code.
The parser supports the observed v0/v1 data layouts; the supplied instance's
version remains unknown until live validation.

- [Authentication and key scopes](https://docs.n8n.io/connect/n8n-api/authentication.md)
- [Workflow API specification](https://docs.n8n.io/connect/n8n-api/workflow.md)
- [Execution API specification](https://docs.n8n.io/connect/n8n-api/executions.md)
- [Pagination](https://docs.n8n.io/connect/n8n-api/pagination.md)
- [Official API security/base specification](https://github.com/n8n-io/n8n/blob/master/packages/cli/src/public-api/v1/openapi.yml)
- [Execution data v1 interface](https://github.com/n8n-io/n8n/blob/master/packages/workflow/src/run-execution-data/run-execution-data.v1.ts)
- [Task data and redacted errors](https://github.com/n8n-io/n8n/blob/master/packages/workflow/src/interfaces.ts)
- [Node API error HTTP code](https://github.com/n8n-io/n8n/blob/master/packages/workflow/src/errors/node-api.error.ts)

## Remaining work

Real n8n connectivity, customer workflow behavior, and Nebius connectivity remain
unverified. No infrastructure adapter, database, tool registry, agent loop,
incidents, remediation, recovery orchestration, frontend, or deployment was
added. Next is Phase 6 — infrastructure checks, using mocks/local fixtures and
current official provider documentation before any real adapter implementation.
