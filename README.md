# AI Reliability Agent

Backend, website checks, and Nebius client for a reliability agent that will investigate website,
n8n/business automation, and infrastructure failures using operational evidence.

## Current scope

- FastAPI backend with `GET /health` and local API documentation.
- Validated environment configuration using Pydantic Settings.
- Application lifecycle logging without configuration dumps or request bodies.
- Automated endpoint/configuration tests, lint, and formatting checks.
- Locked runtime and development dependencies with distribution hashes.
- A bounded Nebius text-inference client and an opt-in live connectivity command.
- Registered website HTTP/endpoint, latency, DNS, and TLS checks with normalized evidence.
- Playwright/Chromium synthetic booking flows with UI verification and frontend error counts.

`/health` reports **backend process liveness only**. It does not claim that
Nebius, n8n, a website, or a database is connected or healthy. The Nebius adapter
is implemented and mock-tested; its real connectivity test still needs an API
key. Website checks pass local fixtures and a public `example.com` smoke check.
n8n and database adapters have not been implemented. No provider
credentials are required to start the backend or run the automated tests.

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
Docs and OpenAPI routes are disabled with `ENVIRONMENT=production`; production
deployment and its security configuration remain future work.

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
flows are implemented; the next phase is the read-only n8n integration.
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

Docker is optional for the overall architecture and is not needed locally.
Choose the backend host before deciding whether deployment needs a container.
No Dockerfile, frontend, database, or empty future adapter files are included.

## Documentation checked for Phase 1

- [FastAPI first steps](https://fastapi.tiangolo.com/tutorial/first-steps/)
- [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
- [uv environment variables](https://docs.astral.sh/uv/reference/environment/)
- [Starlette TestClient requirements](https://github.com/Kludex/starlette/blob/main/docs/testclient.md)

See `docs/PHASE-1.md`, `docs/PHASE-2.md`, `docs/PHASE-3.md`, and `docs/PHASE-4.md` for validation results and `docs/HANDOFF.md`
for the original requirements. No public software license has been selected.
