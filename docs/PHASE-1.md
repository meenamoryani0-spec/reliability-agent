# Phase 1 milestone — 9 October 2026

## Result: PASS

- Python 3.12.14 runs from D:, with a dedicated project virtual environment on D:.
- Complete current pytest suite: **12 passed**.
- Ruff lint and formatting checks pass.
- Real Uvicorn subprocess HTTP smoke: `/health` returns **200** with
  `{"status":"ok","service":"reliability-agent-backend"}`.
- Live `/openapi.json` includes `/health`; `/docs` returns **200**.
- The smoke process is stopped after verification.
- No external provider integrations were implemented or claimed as tested.

## Files created

```text
AGENTS.md
README.md
.gitignore
.env.example
backend/requirements.in
backend/requirements.txt
backend/requirements-dev.in
backend/requirements-dev.txt
backend/pyproject.toml
backend/app/__init__.py
backend/app/config.py
backend/app/logging.py
backend/app/main.py
backend/app/api/__init__.py
backend/app/api/health.py
backend/tests/conftest.py
backend/tests/test_config.py
backend/tests/test_health.py
scripts/environment.ps1
scripts/setup.ps1
scripts/run.ps1
scripts/test.ps1
scripts/smoke.ps1
scripts/smoke.py
docs/HANDOFF.md
docs/PHASE-1.md
```

Local ignored/generated directories: `.venv/`, `work/` (caches, test temporary
files, and smoke logs). Interpreter and standard library:
`D:\CODEX MAIN\2026-10-09\g\work\python-3.12.14`.

## Commands run

From the project root, unless noted:

```powershell
# Inspect workspace and interpreter availability.
Get-ChildItem -Force
git rev-parse --show-toplevel
uv --version
uv python find --no-python-downloads

# Copy existing runtime's interpreter and stdlib to D:, excluding site-packages.
# Create the initial environment (setup.ps1 now uses Python's built-in venv).
uv venv --python 'D:\CODEX MAIN\2026-10-09\g\work\python-3.12.14\python.exe' .venv

. .\scripts\environment.ps1
uv pip compile backend\requirements.in --python $ProjectPython --generate-hashes --output-file backend\requirements.txt
uv pip compile backend\requirements-dev.in --constraint backend\requirements.txt --python $ProjectPython --generate-hashes --output-file backend\requirements-dev.txt
.\scripts\setup.ps1 -PythonExe 'D:\CODEX MAIN\2026-10-09\g\work\python-3.12.14\python.exe'
.\scripts\test.ps1
.\scripts\run.ps1
.\scripts\smoke.ps1
git init --initial-branch=main
```

Additional checks: `pip check`, `git check-ignore` for secrets/runtime/scratch
paths, and `git diff --check`. Stable foundation committed locally; no GitHub
remote or deployment was created.

## Tests

- Liveness status code, JSON content type, and exact response.
- Health disallows POST; future diagnosis endpoint is absent.
- Health appears in local OpenAPI; local documentation loads.
- Production disables docs/OpenAPI while retaining health.
- Configuration defaults do not require credentials.
- Environment values override dotenv configuration.
- Unsupported environment/log-level values fail validation.
- Validation error text does not echo invalid input values.
- `.env.example` is accepted.
- Dotenv path stays anchored to the repository root.

## Problems found and addressed

1. Python on PATH was an unusable Windows alias. Copied the working bundled
   Python runtime to D: and created the virtual environment there.
2. uv wheel installation hit Windows access-denied cache errors, including with
   copy mode/no-cache. Switched setup to Python venv/ensurepip plus pip with
   hash-verified lockfiles and a D: cache. Installation succeeded.
3. Current Starlette warned that TestClient prefers httpx2. Verified its official
   documentation and installed httpx2 as a development dependency. Tests pass
   with warnings treated as errors; HTTPX remains available for future adapters.
4. The execution policy rejected the hidden background launch. The normal run
   script started Uvicorn successfully. Cross-session HTTP requests timed out,
   while a real server/client smoke test within one execution passed. This
   suggests a tool-session boundary limitation; its exact cause is unverified.

No remaining Phase 1 application errors were observed in the completed checks.
Production deployment, monitoring health, provider connectivity, and recovery
verification have not been tested because they are outside this phase.

## Next proposed phase

**Phase 2 — Nebius/Nemotron integration.** Verify the current official API and
hackathon-eligible model, implement a small client, and test a real request using
configured credentials. Stop here until that phase is authorized.

Docker is optional overall; decide whether to use it when choosing backend
hosting. It is not required for the local foundation.
