# AI Reliability Agent

Phase 1 foundation for a reliability agent that will investigate website,
n8n/business automation, and infrastructure failures using operational evidence.

## Current scope

- FastAPI backend with `GET /health` and local API documentation.
- Validated environment configuration using Pydantic Settings.
- Application lifecycle logging without configuration dumps or request bodies.
- Automated endpoint/configuration tests, lint, and formatting checks.
- Locked runtime and development dependencies with distribution hashes.

`/health` reports **backend process liveness only**. It does not claim that
Nebius, n8n, a website, or a database is connected or healthy. Those integrations
have not been implemented. No provider credentials are required in Phase 1.

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
Provider variables will be added alongside their actual integrations.

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
checks health, OpenAPI, and docs over HTTP, and stops the process in cleanup.
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

## Next milestone

Phase 2: verify current official Nebius API documentation and the hackathon's
eligible Nemotron model, implement the client, and smoke-test a real request
with supplied credentials. Do not claim connectivity based on mocked tests.

Docker is optional for the overall architecture and is not needed locally.
Choose the backend host before deciding whether deployment needs a container.
No Dockerfile, frontend, database, or empty future adapter files are included.

## Documentation checked for Phase 1

- [FastAPI first steps](https://fastapi.tiangolo.com/tutorial/first-steps/)
- [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
- [uv environment variables](https://docs.astral.sh/uv/reference/environment/)
- [Starlette TestClient requirements](https://github.com/Kludex/starlette/blob/main/docs/testclient.md)

See `docs/PHASE-1.md` for the actual validation results and `docs/HANDOFF.md`
for the original requirements. No public software license has been selected.
