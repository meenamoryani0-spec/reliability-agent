# AI Reliability Agent

Backend, website checks, and Nebius client for a reliability agent that will investigate website,
n8n/business automation, and infrastructure failures using operational evidence.

## Release status

The application has a locally verified FastAPI backend and Next.js operator
workspace. Authenticated deployment preparation is implemented; cloud deployment,
Linux container execution, and live Nebius/provider integrations remain unverified.
The phase sections below record incremental implementation. For the current
boundaries, read [CURRENT-STATE.md](docs/CURRENT-STATE.md) and
[DEPLOYMENT.md](docs/DEPLOYMENT.md).

## Quick start: local synthetic demo on Windows

Prerequisites: Git, Python 3.12 with the Windows `py` launcher, Node.js 24 with npm
on PATH, PowerShell, and network access for dependency installation. Run the clone
command from the directory where you want the project; this development workspace
keeps project files on D:.

```powershell
git clone https://github.com/meenamoryani0-spec/reliability-agent.git
Set-Location .\reliability-agent
$DemoPython = (py -3.12 -c "import sys; print(sys.executable)").Trim()
.\scripts\setup.ps1 -PythonExe $DemoPython
.\scripts\frontend-setup.ps1
.\scripts\browser-install.ps1
.\scripts\frontend-check.ps1
.\scripts\frontend-demo.ps1 -Port 3000
```

Open <http://127.0.0.1:3000/dashboard>. Ctrl+C stops the preview. It uses a fresh
scratch SQLite database, scripted model responses, and labeled synthetic provider
fixtures. It makes no live provider or inference requests and needs no cloud
account, API key, or paid service. This preview does not establish live Nemotron
integration or complete the hackathon demonstration. The setup commands download
dependencies; caches, browser binaries, logs, and scratch data stay in ignored
project `work/` directories.

## License

Original project source is available under the [MIT License](LICENSE).
Third-party dependencies, including Psycopg (LGPL), Certifi (MPL), and the Geist
font (SIL Open Font License), retain their own licenses and notices. Dependencies
are installed separately through the lockfiles; the project license does not
relicense those packages, model weights, or external services.

## Current scope

- FastAPI backend with `GET /health` and local API documentation.
- Validated environment configuration using Pydantic Settings.
- Application lifecycle logging without configuration dumps or request bodies.
- Automated endpoint/configuration tests, lint, and formatting checks.
- Locked runtime and development dependencies with distribution hashes.
- A bounded Nebius text-inference client and an opt-in live connectivity command.
- Registered website HTTP/endpoint, latency, DNS, and TLS checks with normalized evidence.
- Playwright/Chromium synthetic booking flows with UI verification and frontend error counts.
- Read-only n8n workflow/execution inspection with sanitized node error evidence and local fixtures.
- Read-only Vercel deployment/events, Supabase project/service-health, and PostgreSQL probes.
- Application history storage, explicit Alembic migrations, and service/check/incident repositories.
- A strict internal registry of 13 bounded monitoring tools, with a local tool catalog.
- A bounded model/tool investigation loop with validated evidence-linked conclusions.
- Opt-in automatic incidents from persisted unhealthy checks, with deduplication and evidence links.
- A separately approved, one-shot n8n execution retry with a durable audit and operator CLI.
- Separate recovery verification with durable node evidence before scoped incident resolution.
- A local Next.js/TypeScript dashboard for service signals, incidents, evidence,
  investigation, approval/action audit, and historical recovery proof.

## Dashboard — Phase 13

```powershell
.\scripts\frontend-setup.ps1
.\scripts\frontend-check.ps1
# Populated synthetic preview in a fresh scratch database:
.\scripts\frontend-demo.ps1 -Port 3000
```

Open <http://127.0.0.1:3000>. For the existing configured backend, run
`scripts/run.ps1` and `scripts/frontend-run.ps1` in separate terminals instead.
Refresh reads history, not fresh provider checks. Source labels, evidence ages,
unknown causes, and recovery scope stay explicit. All history views are bounded
to the latest 100 records. Remediation/approval/verification remain local operator
CLI actions. Production authentication is implemented in Phase 14; actual cloud
deployment remains pending.
See [frontend/README.md](frontend/README.md) for setup, behavior, limits, and checks.

`/health` reports **backend process liveness only**. It does not claim that
Nebius, n8n, a website, or a database is connected or healthy. The Nebius adapter
is implemented and mock-tested; its real connectivity test still needs an API
key. Website checks pass local fixtures and a public `example.com` smoke check.
The n8n adapter passes fixture/mock tests; real n8n connectivity remains unverified.
Infrastructure adapters pass mocks/fixtures; live Vercel, Supabase and PostgreSQL
connections remain unverified. Application history supports a local SQLite file
and a separate PostgreSQL application database. Migrations and persistence are
tested on both engines, including a real isolated PostgreSQL server. No cloud
credentials are required for local development.

## Layout on this computer

```text
D:\CODEX MAIN\2026-10-09\g\
  outputs\reliability-agent\    Git repository and deliverable
    backend\app\               Application code
    backend\tests\             Automated tests
    scripts\                   Setup, run, and test commands
    docs\                      Handoff and milestone evidence
    .venv\                     Installed dependencies (ignored)
    work\                      Cache, temporary files, logs (ignored)
  work\python-3.12.14\         Local Python interpreter and standard library
```

The local Python runtime was copied from the existing Codex runtime, excluding
its site-packages. All newly created project/runtime files are on D:. Git and uv
use existing executables installed on the computer. The original attached
handoff remains at its original attachment location; a copy is in `docs/`.

## Setup (PowerShell)

From the repository root:

```powershell
Set-Location 'D:\CODEX MAIN\2026-10-09\g\outputs\reliability-agent'
.\scripts\setup.ps1 -PythonExe 'D:\CODEX MAIN\2026-10-09\g\work\python-3.12.14\python.exe'
```

Requires Python with venv/ensurepip and network access for the initial dependency download.
The scripts put caches and temporary files inside the ignored project `work/`
directory. No virtual environment activation is necessary. On another computer,
pass the path of an installed Python 3.12+ interpreter to `-PythonExe`.

Defaults work without `.env`. If configuration changes are needed:

```powershell
Copy-Item .env.example .env
```

The app loads `.env` from the repository root, independent of the shell's
working directory. Environment variables take precedence. Invalid values and
unknown dotenv entries fail configuration validation. `.env` is ignored by Git.
The Nebius variables are defined in `.env.example`; later providers will be added
alongside their actual integrations.

## Run and verify

```powershell
.\scripts\run.ps1
```

In another PowerShell terminal:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

Expected response:

```json
{"status":"ok","service":"reliability-agent-backend"}
```

Local documentation: <http://127.0.0.1:8000/docs>. Stop the foreground server
with Ctrl+C. Use `-Port 8001` if port 8000 is occupied. The launch script binds
to loopback and disables access logs to avoid capturing URLs/query strings.
Docs and OpenAPI routes are disabled with `ENVIRONMENT=production`. Authenticated
production configuration is described in [DEPLOYMENT.md](docs/DEPLOYMENT.md);
actual cloud deployment remains unverified.

## Tests and code checks

```powershell
.\scripts\test.ps1
.\scripts\smoke.ps1
```

This runs pytest, Ruff lint, and Ruff formatting validation. Pytest temporary
files are placed under `work/pytest`; that directory is disposable test output.
The smoke script starts a real Uvicorn subprocess on an available loopback port,
checks health, OpenAPI, docs, the website registry, and rejected check requests
over HTTP, and stops the process in cleanup.
Its server log is in `work/logs/smoke-server.log`. This also supports tool sessions
where a separately launched server is unreachable from another execution.

## Dependencies

uv on PATH is only needed to regenerate dependency lockfiles.
`requirements.in` defines runtime dependencies; `requirements-dev.in` adds test
and code-check tools. Commit the generated `.txt` lockfiles. After deliberately
changing dependencies, regenerate and test both lockfiles:

```powershell
. .\scripts\environment.ps1
uv pip compile backend\requirements.in --python $ProjectPython --generate-hashes --output-file backend\requirements.txt
uv pip compile backend\requirements-dev.in --constraint backend\requirements.txt --python $ProjectPython --generate-hashes --output-file backend\requirements-dev.txt
.\scripts\setup.ps1 -PythonExe 'D:\CODEX MAIN\2026-10-09\g\work\python-3.12.14\python.exe'
.\scripts\test.ps1
```

## Nebius connection — Phase 2

Official documentation checked on 9 October 2026 identifies the public model
`nvidia/Nemotron-3_5-Lightning` and the REST API base
`https://api.tokenfactory.nebius.com/v1/`. The client uses HTTPX directly.

Create a key through [Nebius Token Factory](https://tokenfactory.nebius.com/),
then edit the ignored repository-root `.env` locally. Put the key after
`NEBIUS_API_KEY=`; never paste it into chat or commit it. A blank `.env` has been
created on this computer, without overwriting an existing configuration.

```powershell
.\scripts\nebius-smoke.ps1
```

The command checks the selected model using `GET /v1/models`, then makes one
`POST /v1/chat/completions` request with a static greeting prompt. This can
consume provider credits. It prints only PASS and model metadata; neither the
key nor the response text is printed. No automatic retries are performed.

Missing credentials, authorization failures, rate limiting, timeouts, malformed
payloads, oversized output, truncated completions, empty text, and a mismatched
model produce a sanitized NOT_VERIFIED reason. These are connection/check
failures and are not diagnoses of a monitored service.

**Local development does not require a Nebius API key.** Following the user's
10 October 2026 clarification, development can continue with mocked provider
responses and local fixtures. Website checks and synthetic Playwright booking
flows, read-only n8n inspection and infrastructure checks are implemented;
database persistence, the AI tool registry and the investigation loop are also
implemented, including opt-in incidents and the first approved n8n retry action.
Recovery verification and the local dashboard are implemented.
The Nebius client is implemented and mock-tested; real connectivity remains
unverified until the live request passes. Require live integration and end-to-end
validation before presenting the complete application as working.
See `docs/PHASE-2.md` for evidence.
Local async tests require loopback socket access on Windows; this tool's
restricted execution environment required network permission for asyncio startup.

## Website checks — Phase 3

Website checks run in ordinary Python and do not call Nebius or require an API key.
Add operator-controlled targets to `.env`, then restart the backend:

```dotenv
WEBSITE_TARGETS=[{"id":"demo","url":"https://your-site.example/health","expected_statuses":[200],"latency_warning_ms":2000}]
WEBSITE_DNS_NAMESERVERS=[]
```

Replace the example hostname with a real public website. Register separate IDs
for a homepage and an API health endpoint if both need checking. Up to 25 targets
are supported. Targets require a DNS hostname, HTTP or HTTPS, and its default
port; credentials, query strings, fragments, literal IPs, and local names are
rejected. The API accepts a registered ID, never an arbitrary URL.

```powershell
Invoke-RestMethod http://127.0.0.1:8000/services/websites
Invoke-RestMethod -Method Post 'http://127.0.0.1:8000/checks/websites/demo?kind=http'
Invoke-RestMethod -Method Post 'http://127.0.0.1:8000/checks/websites/demo?kind=dns'
Invoke-RestMethod -Method Post 'http://127.0.0.1:8000/checks/websites/demo?kind=ssl'
```

Each result includes the component, check type, status, severity, safe summary,
evidence, timestamp, and optional latency. `healthy` is true for HEALTHY, false
for UNHEALTHY, and null for DEGRADED, UNKNOWN, or CHECK_FAILED.

| Check | What it verifies |
| --- | --- |
| HTTP | Expected success status and time through DNS, connection, redirects, and response headers; response bodies are not read |
| DNS | A/AAAA lookup using the OS-configured resolver, with every returned address checked against the public-destination policy |
| TLS | Trusted certificate chain and hostname, expiry warning within 30 days, negotiated TLS version |

All answers must be public addresses. HTTP/TLS probes use the first sorted
address, preferring IPv4, with the original Host header and TLS SNI. Addresses
are pinned through at most three same-host redirects; HTTPS downgrades and
cross-host redirects are rejected. Checks have a 10-second total deadline,
with up to one extra second for TLS cleanup. There is no automatic retry.

Expected status defaults to 200; only 200–299 statuses can be configured.
Unexpected statuses such as 404/500 are UNHEALTHY. A slow expected response or
429 is DEGRADED; 401/403 is CHECK_FAILED because this probe has no credentials.
NXDOMAIN/no address records is UNHEALTHY. Resolver failures, unsafe destinations,
connection errors, and timeouts are CHECK_FAILED. Plain HTTP has UNKNOWN TLS
status. A certificate verification failure is UNHEALTHY; the checker does not
invent expiry details when the TLS handshake cannot provide a verified certificate.

The optional `WEBSITE_DNS_NAMESERVERS` JSON list overrides DNS **inside this app**,
using up to three public DNS IPs. Empty uses the OS configuration. In this tool
sandbox, dnspython found no OS nameservers; `dns_resolver_not_configured` identifies
that problem. The public smoke check passed with `["1.1.1.1"]`. This does not
change Windows DNS settings.

Run an opt-in live check of a configured target:

```powershell
.\scripts\website-smoke.ps1 -TargetId demo
```

It prints normalized evidence and exits successfully only when DNS, HTTP, and
TLS are all HEALTHY. HTTP-only targets therefore report ATTENTION for their
UNKNOWN TLS check. Scheduled monitoring, persistence, customer browser flows, and
business-process diagnosis are later phases. Checks of one selected address
do not establish the health of every server behind a hostname.
See `docs/PHASE-3.md` for actual validation results.

## Browser business-flow checks — Phase 4

Install the pinned dependencies with the existing setup command, then install
Chromium's headless shell on D: (no Chrome installation or API key needed):

```powershell
.\scripts\browser-install.ps1
.\scripts\test.ps1
.\scripts\browser-smoke.ps1
```

The browser smoke starts a real Uvicorn server, calls both flow endpoints over
HTTP, checks their expected statuses, and stops the server. Sanitized browser
results are saved to `work/evidence/browser-smoke.json`.

With the backend running, these are also available in local API documentation:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/services/browser-flows
Invoke-RestMethod -Method Post http://127.0.0.1:8000/checks/browser-flows/booking-healthy
Invoke-RestMethod -Method Post http://127.0.0.1:8000/checks/browser-flows/booking-crm-failure
```

| Flow | Evidence required | Status |
| --- | --- | --- |
| `booking-healthy` | Navigation 200, booking POST 200, visible confirmation, no frontend errors | HEALTHY |
| `booking-crm-failure` | Navigation 200, simulated booking POST 502, visible failure, no confirmation | UNHEALTHY |

These are **synthetic fixtures in a real Chromium browser**. HTML and API
responses are fulfilled locally by Playwright at a fixed `.test` origin;
no website, CRM, calendar, WhatsApp service, or n8n instance is contacted.
Every other routed request is aborted. Service workers and downloads are
disabled. The form uses a synthetic customer and never creates a real booking.
The simulated authentication rejection is fixture evidence, not a verified
root cause in any customer's system.

Each check launches an isolated Python worker and fresh browser context, fills
the form, submits it, and verifies visible UI output as well as response status.
Console errors and uncaught page errors are counted. Raw error messages, page
content, exception details, screenshots, and traces are not returned or saved.
An otherwise successful flow with frontend errors is DEGRADED.
Missing Chromium, deadlines, blocked requests, or unverified UI results are
CHECK_FAILED with `healthy: null`, rather than evidence a customer service is broken.

Only these two fixed flow IDs are accepted. Demo endpoints return 404 in
production; configurable customer flows and their network/write policies remain
future work. One worker may run per backend process; overlapping checks report
`browser_busy`. The worker has a 30-second deadline, followed by up to 10 seconds
for termination cleanup. Windows uses process-tree termination on timeout.
The subprocess avoids coupling Playwright to Uvicorn's Windows event loop and
inherits no provider keys or proxy settings.

Browser binaries, disposable browser profiles, temporary files, and Python caches
use ignored `work/` directories on D:. In this Windows sandbox, Node archive
extraction failed with `EPERM` at `realpath`. If the normal installer fails that
way, run `.\scripts\browser-install.ps1 -UseArchiveFallback`. This downloads and
extracts the exact official CDN archives reported by the installed Playwright
CLI into the same D: directory, with archive path/size validation. No SDK files,
OS permissions, or browser launch security settings are patched.
Chromium must be installed before running the full test suite; browser tests fail
if the browser is missing, rather than silently skipping real execution.
See `docs/PHASE-4.md` for verified milestone evidence.

## Read-only n8n inspection — Phase 5

Run the local demo without API credentials:

```powershell
.\scripts\n8n-smoke.ps1
```

This starts a real FastAPI/Uvicorn backend with `N8N_MODE=fixture`, inspects the
synthetic workflow and two saved execution records over HTTP, verifies the
results, and stops the backend. The n8n provider itself is an in-memory fixture;
no n8n instance, CRM, or customer is contacted. Sanitized results are written to
`work/evidence/n8n-smoke.json`.

To inspect the same fixtures with the normal backend command, set
`N8N_MODE=fixture` in the ignored `.env`, then run `scripts/run.ps1`. The default
is `disabled`; missing live configuration does not prevent backend startup.

```powershell
Invoke-RestMethod http://127.0.0.1:8000/services/n8n
Invoke-RestMethod http://127.0.0.1:8000/n8n/workflows
Invoke-RestMethod 'http://127.0.0.1:8000/n8n/executions/failed?workflow_id=wf-booking'
Invoke-RestMethod http://127.0.0.1:8000/n8n/executions/1001
Invoke-RestMethod http://127.0.0.1:8000/n8n/executions/1002
```

Execution `1001` has recorded state `error`, node ID `crm`, and node HTTP 401.
It returns UNHEALTHY with `authentication_rejected`; the downstream
`confirmation` node has no recorded run in that fixture. Execution `1002` has
recorded state `success` with all three nodes observed. This does not prove
delivery to a customer. With INCIDENTS_ENABLED=true, unhealthy synthetic checks
can create synthetic incidents; no incident is resolved automatically.

Read responses use `status: OK` for a completed inspection and `CHECK_FAILED`
for an inspection failure. `OK` does not mean the workflow is healthy. Details
contain their own execution status. `root_cause_verified` and
`business_outcome_verified` remain false. A recorded HTTP 401 cannot establish
whether a credential expired, was revoked, or was configured incorrectly.
HTTP 403 is classified separately as `permission_denied`.

Optional future live configuration, in the ignored `.env` only:

```dotenv
N8N_MODE=live
N8N_BASE_URL=https://your-instance.example/api/v1/
N8N_API_KEY=
N8N_TIMEOUT_SECONDS=10
N8N_DNS_NAMESERVERS=[]
```

Use the actual public HTTPS API root and set its key locally. The client sends
`X-N8N-API-KEY` and permits only GET for `/workflows`, `/executions?status=error`,
and `/executions/{id}?includeData=true`. The error list covers the provider's
`error` status, not canceled or crashed runs. No retry, execution, activation,
deactivation, credential access, or workflow modification method is implemented.
Where scoped keys are available, use `workflow:list`, `execution:list`, and
`execution:read`. n8n's documentation says non-Enterprise keys have full account
capabilities; this application's GET restriction does not change key permissions.
[Official authentication/scopes reference](https://docs.n8n.io/connect/n8n-api/authentication.md).

Live destinations must be operator-configured public DNS hostnames, HTTPS on the
default port, with an API root ending in `/api/v1/`. Subpath installations are
supported. Local/private self-hosted endpoints require a future explicit network
policy. Credentials in URLs, query strings, fragments, and literal IPs are
rejected. All DNS addresses must pass the existing public-address policy; the
selected address is pinned while preserving Host/TLS SNI. Proxies and redirects
are disabled. `N8N_DNS_NAMESERVERS` optionally selects up to three public DNS IPs
inside this app without changing Windows settings.

Each inspection makes one provider request with a total deadline (10 seconds by
default; configurable 1–30) and a 1 MiB decoded response limit. Lists return one
page of at most 50 records, with `next_cursor` for explicit subsequent requests;
there is no automatic pagination. Normalization accepts execution data versions
0/1 and bounds node counts, attempts, and errors. Unknown/malformed/contradictory
data is CHECK_FAILED. Missing, redacted, or size-suppressed data is identified;
the client does not override redaction or request oversized data to be revealed.

Only validated IDs, timestamps, states, opaque cursors, fixed error categories,
HTTP codes, and hashed node references are retained. Workflow names, node names,
parameters, credentials, node inputs/outputs, raw messages, stacks, and response
bodies are not returned or logged. Hashed references are technical identifiers,
not an anonymity guarantee. The API key is masked in configuration and rejected
if a provider echoes it in retained result fields.

The local n8n routes are disabled in production until deployment access controls
are implemented. Synthetic mode is also rejected by production settings.
`services/n8n` reports configuration only, not connectivity or workflow health.
See `docs/PHASE-5.md` for verified evidence.

## Infrastructure checks — Phase 6

Run `scripts/infrastructure-smoke.ps1` without credentials. It starts a real
Uvicorn/FastAPI server, checks five endpoints over HTTP, saves sanitized results
to `work/evidence/infrastructure-smoke.json`, and stops the server. The provider
responses use HTTPX mocks; PostgreSQL uses a fake driver, not a SQL server.

For interactive exploration, set `INFRASTRUCTURE_MODE=fixture` in the ignored
repository-root `.env`, run `scripts/run.ps1`, and open local `/docs`.

```powershell
Invoke-RestMethod http://127.0.0.1:8000/services/infrastructure
Invoke-RestMethod -Method Post http://127.0.0.1:8000/checks/infrastructure/vercel-deployment
Invoke-RestMethod -Method Post http://127.0.0.1:8000/checks/infrastructure/vercel-events
Invoke-RestMethod -Method Post http://127.0.0.1:8000/checks/infrastructure/supabase-project
Invoke-RestMethod -Method Post http://127.0.0.1:8000/checks/infrastructure/supabase-health
Invoke-RestMethod -Method Post http://127.0.0.1:8000/checks/infrastructure/postgres
```

| Check | Evidence and limits |
| --- | --- |
| `vercel-deployment` | Configured deployment ID and readyState; READY does not verify production alias or business health |
| `vercel-events` | Up to 25 build event types/timestamps; no raw log text; always UNKNOWN health |
| `supabase-project` | Configured project reference and provider-reported project state |
| `supabase-health` | Complete, consistent provider reports for db, auth and rest only |
| `postgres` | Fixed SELECT 1 plus transaction_read_only; require `(1, 'on')` |

Modes are `disabled` (default), `fixture` and opt-in `live`. Missing live settings
do not prevent startup. The registry reports configuration only. Results
separate `inspection` from `status`, and always leave root cause and business
outcome unverified. Authentication, rate-limit, DNS, transport, invalid-response
and database access errors are CHECK_FAILED with `healthy: null`.

Vercel ERROR/BLOCKED are unhealthy deployment states; canceled/in-progress states
are UNKNOWN. Supabase ACTIVE_UNHEALTHY and explicit initialization/restore/pause
failures are UNHEALTHY; inactive/transitional project states are UNKNOWN. Service
COMING_UP is DEGRADED. Missing/duplicate/contradictory health reports fail checks.

Optional live settings are in `.env.example`. Set `INFRASTRUCTURE_MODE=live`:

- Vercel: `VERCEL_TOKEN`, `VERCEL_DEPLOYMENT_ID` (`dpl_...`), optional `VERCEL_TEAM_ID`.
- Supabase: `SUPABASE_ACCESS_TOKEN` (Management API token), `SUPABASE_PROJECT_REF` (20 lowercase letters). Project anon/service-role keys are not Management API tokens.
- PostgreSQL: `POSTGRES_HOST`, `POSTGRES_PORT` (5432/6543), `POSTGRES_DBNAME`, `POSTGRES_USER`, `POSTGRES_PASSWORD`. Use a dedicated least-privilege login.

Keep secrets in ignored environment configuration. There are no arbitrary URL,
DSN or SQL inputs. Inspection routes and fixtures are disabled in production
until deployment access controls exist. The read-only probe does not revoke a
database login's privileges elsewhere.

HTTP clients use fixed official hosts, HTTPS, public DNS validation, IP pinning
and original Host/TLS SNI. Proxies, redirects, retries and automatic pagination
are disabled. Total timeout defaults to 10 seconds (configurable 1–30); decoded
response limit is 1 MiB. Events are a sample, not complete logs.

PostgreSQL accepts one public DNS hostname. Psycopg/libpq pins a validated IP
using `hostaddr`, preserving `host` for TLS identity. Live probes use a separate
process; the password travels via stdin, not command-line arguments. Unrelated
credentials, proxy and PG environment settings are excluded. TLS is verify-full
using the pinned Certifi CA bundle; client certificates and GSS/SSPI are disabled.
Only password/SCRAM authentication is allowed. Private/self-signed databases
need a future explicit network/CA policy.

The worker executes one static read-only query with server-side statement/lock
timeouts. The caller deadline includes DNS/startup; worker communication uses
the remaining budget, with up to ten seconds for process termination cleanup.
Overlapping probes fail while that worker slot is occupied. No application
tables, models, migrations or arbitrary queries were added. See `docs/PHASE-6.md`.

## Application history — Phase 7

Application storage is separate from the monitored `POSTGRES_*` database.
It stores monitored service identities, check results, and the initial incident
records. Phase 10 adds opt-in automatic detection; Phase 12 adds scoped
resolution only after successful verification, described below.

On this computer local history is enabled in the ignored `.env`, with the
database at `work/data/reliability.sqlite3` on D:. On a fresh checkout, configure:

```dotenv
STORAGE_MODE=local
STORAGE_SQLITE_FILE=work/data/reliability.sqlite3
```

Then run the explicit migration and backend:

```powershell
.\scripts\migrate.ps1 -Action upgrade
.\scripts\run.ps1
```

`migrate.ps1 -Action status` checks revision without upgrading. Startup and HTTP
routes never apply migrations. Migration `0001_history` creates only application
tables: `monitored_services`, `checks`, and `incidents`. Migration
`0002_incident_detection` adds evidence links/deduplication;
`0003_incident_assessments` stores supported diagnoses/recommendations. Current
`0004_approved_n8n_retry` adds approval/dispatch audit; current head
`0005_verified_recovery` adds guarded verification/resolution. PostgreSQL uses the
separate `reliability` schema; SQLite uses the configured local file. Existing
customer/provider tables are never used for application history.

When enabled, website/browser/infrastructure checks and n8n execution-detail
inspections record observations. n8n workflow/execution list pages are not health
observations and are not recorded. Response bodies remain compatible; headers
`X-History-Status` and `X-Check-Id` indicate whether a result was saved and its ID.
An unavailable database does not change the health result or backend liveness;
the response explicitly reports `unavailable` when the save fails.

```powershell
Invoke-RestMethod http://127.0.0.1:8000/storage
Invoke-RestMethod 'http://127.0.0.1:8000/history/services?limit=25'
Invoke-RestMethod 'http://127.0.0.1:8000/history/checks?limit=25&synthetic=true'
Invoke-RestMethod http://127.0.0.1:8000/history/incidents
```

History reads support bounded pagination (1–100 records, offset 0–10000), service
IDs and check-status/synthetic filters. Detail reads use UUIDs. History routes
are disabled in production pending authentication and deployment access controls.
No public history-write, SQL, database-deletion or migration endpoint exists.

Service identity includes the component, target fingerprint and synthetic flag.
Changing targets or switching fixture/live data creates a distinct service.
Only allowlisted normalized evidence is stored, at most 64 KiB per check;
free-text summaries/logs and source connection strings are not stored. Source
fingerprints are not an anonymity guarantee. Timestamps round-trip as UTC.

The repository uses per-operation sessions/transactions, parameterized SQL,
foreign keys, indexes and conflict-safe first registration. Failed transactions
roll back. Incident records reference a specific unhealthy check on the same
service. Incidents start OPEN/INVESTIGATING; Phase 12 permits RESOLVED only
with a stored VERIFIED proof and healthy evidence on the same service.

For the dedicated PostgreSQL application database:

```dotenv
STORAGE_MODE=postgresql
STORAGE_DATABASE_URL=postgresql+psycopg://app_user:password@database.example:5432/app_database
STORAGE_ALLOW_LOOPBACK=false
```

Keep the real URL only in ignored environment configuration. Query-string/DSN
options are rejected; remote TLS is forced to verify-full using Certifi. Schema
upgrades are an explicit operator action. Use a dedicated application database
and appropriate schema permissions. Supabase/cloud connectivity and production
permissions remain unverified. Test-only loopback/plaintext requires explicit
opt-in and is rejected in production, as is local SQLite storage.

Run `scripts/storage-smoke.ps1` to migrate a new scratch file, execute actual
backend fixture checks, restart Uvicorn, and verify persisted results. For real
PostgreSQL integration use `scripts/postgres-integration.ps1`; this computer has
the portable EDB binaries under ignored `work/postgres-runtime/`. The harness
creates a random isolated cluster/database on loopback, runs the complete test
suite, and stops the server. It installs no Windows service. Cloud credentials
are never used. Other machines can pass `-BinDir` after placing official binaries
inside project `work/`. PostgreSQL tests skip explicitly without the harness.

See `docs/PHASE-7.md` for validation details and limits.

## AI tool registry — Phase 8

`GET /tools` lists 13 fixed function descriptors and their execution policy.
The internal registry accepts validated JSON arguments and calls the existing
monitoring adapters. It exposes no shell, SQL, arbitrary URL, incident-write or
remediation operation. Tool execution has no public HTTP endpoint. Production
catalog/internal access remains disabled pending deployment access controls.

Calls accept at most 4 KiB of JSON, return at most 64 KiB of canonical JSON, and
allow one in-flight registry operation. IDs, types, extra fields and pagination
are checked before I/O. Existing provider deadlines/network policies remain in
force. A timeout keeps the slot occupied until underlying work finishes.
Results preserve fixture labels and distinguish dispatch success from service
health. History failure is reported separately from operational evidence.

```powershell
.\scripts\tools-smoke.ps1
```

This runs real Chromium with intercepted fixtures, n8n/infrastructure fixtures,
and new scratch SQLite history, then verifies the catalog over actual Uvicorn
HTTP. No provider credentials or model request are needed. The investigation
loop is implemented in Phase 9. See `docs/PHASE-8.md` for registry contracts;
Phase 9 successfully reran the PostgreSQL harness in the current environment.

## AI investigation loop — Phase 9

`GET /agent` describes configured inference mode and limits. `POST /investigations`
accepts `{"question":"..."}` and runs the bounded model/tool/evidence cycle.
Model-selected hypotheses must cite actual observations and pass support checks.
Summaries remain scoped to observed failures; root cause and business outcome
stay unverified. With Phase 10 enabled, persisted unhealthy tool observations
create incidents through server policy. The loop performs no remediation.

`INVESTIGATION_MODE` defaults to `disabled`. Run the local fixture smoke:

```powershell
.\scripts\agent-smoke.ps1
```

This uses actual Uvicorn, a scripted model fixture and monitoring fixtures. It
verifies 3 model turns and 4 tools for `Why are booking confirmations missing?`.
The result is explicitly labeled `scripted_fixture`; it is not live Nemotron.
Interactive fixture mode requires investigation, n8n and infrastructure modes
all set to `fixture`. Other fixture questions are rejected.

Opt-in `INVESTIGATION_MODE=live` uses existing Nebius settings and can send the
question/restricted evidence to the provider. Live model availability/tool calling
remain unverified. Each investigation permits at most 6 completion attempts,
8 tools and 120 seconds, with one investigation in flight. Invalid or unsupported
conclusions fail closed while preserving collected evidence. Production access
stays disabled. See `docs/PHASE-9.md` for configuration, contracts and limitations.

Docker is optional for local development. Backend/frontend Dockerfiles and the
Next.js workspace are now included; Linux image execution remains unverified.

## Automatic incidents — Phase 10

`INCIDENTS_ENABLED` defaults to `false`. With migrated application storage and
this flag set to `true`, each persisted `UNHEALTHY` observation automatically
opens or reuses an incident. The policy applies to direct monitoring requests
and investigation tools, independently of model conclusions. No incident-write
tool is exposed to the model. Production enablement is rejected pending controls.

Deduplication uses service identity plus check kind. Source changes and
synthetic/live data keep distinct identities. Repeated failures link additional
check observations to the same unresolved incident. `observation_count` counts
checks, including repeated polling of the same execution; it is not a count of
affected bookings, users or unique provider events. Different causes within one
service/check kind currently share an unresolved incident.

`HEALTHY`, `DEGRADED`, `UNKNOWN`, `CHECK_FAILED` and list metadata create no
incidents. A healthy observation does not resolve an existing incident. Root
cause and business outcome remain unverified; new incidents use policy severity
`high`, which is not independently measured customer impact.

Direct check responses add `X-Incident-Status` (disabled, not_applicable, created,
existing or unavailable) and, only when confirmed, `X-Incident-Id`. A failed
incident transaction preserves the separately committed check. Investigation
reports contain confirmed `incident_ids`; `incident_created` means at least one
incident was confirmed newly created during that run. A deadline may return
unavailable while the worker later commits; read history after it finishes.

```powershell
.\scripts\incidents-smoke.ps1
```

This uses fresh SQLite storage, actual Uvicorn/Chromium and scripted monitoring/
model fixtures, then restarts the server and verifies the same incidents/evidence.
For interactive local use, explicitly migrate before setting the opt-in flag:

```powershell
.\scripts\migrate.ps1 -Action upgrade
$env:INCIDENTS_ENABLED = 'true'
$env:INVESTIGATION_MODE = 'fixture'
$env:N8N_MODE = 'fixture'
$env:INFRASTRUCTURE_MODE = 'fixture'
.\scripts\run.ps1
```

Bounded reads include `GET /history/incidents/{id}` and
`GET /history/incidents/{id}/observations?limit=25&offset=0` and
`GET /history/incidents/{id}/assessments`; incident lists also
support `synthetic=true|false`. No incident create/update/resolve HTTP route,
background polling scheduler or automatic reconciliation exists. Phase 12 adds
a separate operator verification CLI. Phase 11 adds the approved retry below. Existing
development `.env` settings remain unchanged.
A validated investigation conclusion stores an assessment only for cited,
supporting checks linked to an incident. Assessments contain the finite hypothesis,
recommended next steps, actual inference source, timestamp and supporting check
ID. Root cause is explicitly unknown (`null`) and unverified; HTTP 401 alone
cannot establish credential expiry. Invalid conclusions add no diagnosis.
`incident_assessment` reports its separate save outcome. Stored assessments can
survive even if a caller deadline expires before confirmation. Replay preserves
an existing assessment for the same check. No numeric confidence is invented.
See `docs/PHASE-10.md` for migration safeguards, evidence and limitations.

## Approved n8n retry — Phase 11

The first write action, `retry_n8n_execution(execution_id)`, runs through a
**local operator CLI**, separate from the AI registry and HTTP monitoring routes.
It defaults off. Explicit enablement requires migrated application storage,
matching monitoring/retry modes and a nonempty workflow allowlist:

```dotenv
N8N_RETRY_MODE=disabled
N8N_RETRY_WORKFLOW_IDS=[]
```

The operator first creates/reviews a proposal bound to an unhealthy n8n check and
its unresolved incident, then approves the exact action ID with
`--approve-retry-side-effects`. The warning matters: retry can repeat messages,
payments or other external effects. Approval expires within five minutes of
observation capture. Source/mode/workflow eligibility and expiry are rechecked.
A fresh provider read must still show the same original failed execution.

Approval and dispatch intent commit before the fixed POST. The body is always
`{"loadWorkflow":false}`; no arbitrary workflow, URL or action is accepted.
Atomic claims and a unique source/execution key prevent duplicate dispatches
through the shared application database. There is no automatic retry. An
uncertain submission remains blocked across restart; external operators and
provider side effects are outside this local deduplication guarantee.

A validated new-execution receipt means ACCEPTED, not recovered. Incidents remain
OPEN/INVESTIGATING until separate Phase 12 verification succeeds. If audit storage fails, operational evidence and the consumed
intent are preserved, with uncertainty reported separately. The local CLI trust
boundary is not a production authorization system. Production retry is disabled.

```powershell
.\scripts\retry-smoke.ps1
```

This exercises real CLI/Uvicorn processes with a synthetic in-memory n8n provider,
including omitted approval, an accepted retry, duplicate blocking and restart
persistence. No live workflow is executed. `GET /actions` describes policy;
`GET /history/actions` and `/history/actions/{UUID}` expose bounded audit reads.
No HTTP approval/execution route or model retry tool is added; the 13 monitoring
tools remain read-only. See `docs/PHASE-11.md` for operator commands, policy,
migration details, outcomes and limits. Live retry remains unverified.

## Documentation checked for Phase 1

- [FastAPI first steps](https://fastapi.tiangolo.com/tutorial/first-steps/)
- [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
- [uv environment variables](https://docs.astral.sh/uv/reference/environment/)
- [Starlette TestClient requirements](https://github.com/Kludex/starlette/blob/main/docs/testclient.md)

See `docs/PHASE-1.md` through `docs/PHASE-12.md` for validation results and `docs/HANDOFF.md`
for the original requirements. See [License](#license) for the project license.

## Phase 12 — verify an accepted retry

Recovery is off by default. Read [the Phase 12 report](docs/PHASE-12.md) before
enabling it. In a local development/test environment with migrated storage,
set `N8N_RECOVERY_MODE` to the matching n8n `fixture` or `live` mode and configure
`N8N_RECOVERY_FLOWS` as a JSON mapping, for example:

```json
{"wf-booking":{"required_node_ids":["trigger","crm","confirmation"],"completion_node_id":"confirmation"}}
```

Use actual stable workflow/node IDs for a real target. The path must contain
the original failed node(s) and a later completion node. Then, from `backend/`
with the project environment active:

```powershell
python -m app.recovery.cli verify --action-id ACCEPTED_ACTION_UUID
```

One bounded read inspects that action's exact new execution. It does not resend
the retry. Only fresh, complete success evidence at all required nodes can store
proof and resolve the incident in one transaction. Running, failed, unavailable,
stale or incomplete evidence leaves it unresolved. Repeat the command manually
if an earlier read found it still running. A successful repeat after resolution
returns the historical proof and identifies it as reused.

`GET /recovery` describes policy. `GET /history/verifications` and
`GET /history/verifications/{UUID}` read stored attempts. No HTTP/model verification
write path exists. Resolution is scoped to `n8n_required_nodes`; business delivery
and root cause remain unverified. Live integration still needs provider validation.

Migration `0005_verified_recovery` preserves old rows and adds proof guards.
Back up local storage before the explicit migration command. Downgrade refuses
to discard recovery history. Startup does not migrate. The PostgreSQL test harness
also accepts `-TemplateDir` pointing to a verified, cleanly stopped project-only
`work/postgres-tests/cluster-*/data` directory; it copies it, creates a new scratch
database, establishes fresh SCRAM authentication and stops only its own copy.

## Phase 14 - authenticated release preparation

The root is now a product landing page, with the dark operational workspace at
`/dashboard`. See `docs/FRONTEND-REFINEMENT.md` for the visual checkpoint.

Production access now supports a generated single-operator login, signed secure
session, fixed HTTPS frontend-to-backend service token, exact Host/Origin rules,
no browser-to-backend CORS, bounded request budgets and schema-aware `/ready`.
Synthetic browser tools and production remediation remain disabled. Existing
local development and fixture behavior remain available.

`backend/Dockerfile`, `frontend/Dockerfile`, deployment environment templates,
explicit production startup, key generation and TLS/deployed smoke scripts are
prepared. Read `docs/DEPLOYMENT.md` and `docs/PHASE-14.md` before enabling anything.
The local implementation is distinct from an actual cloud deployment. Docker
execution, selected cloud accounts/domains, Supabase TLS/storage and live provider
validation remain outstanding. No cloud resources have been provisioned.
