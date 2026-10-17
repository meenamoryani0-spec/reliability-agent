. (Join-Path $PSScriptRoot 'environment.ps1')
if (-not (Test-Path -LiteralPath $ProjectPython)) { throw 'Run scripts/setup.ps1 first.' }
$env:ENVIRONMENT = 'test'
$env:LOG_LEVEL = 'INFO'
$env:INVESTIGATION_MODE = 'disabled'
$env:INCIDENTS_ENABLED = 'false'
$env:N8N_MODE = 'disabled'
$env:N8N_RETRY_MODE = 'disabled'
$env:N8N_RETRY_WORKFLOW_IDS = '[]'
$env:N8N_BASE_URL = ''
$env:N8N_API_KEY = ''
$env:N8N_DNS_NAMESERVERS = '[]'
$env:INFRASTRUCTURE_MODE = 'disabled'
$env:INFRASTRUCTURE_DNS_NAMESERVERS = '[]'
$env:INFRASTRUCTURE_TIMEOUT_SECONDS = '10'
$env:VERCEL_TOKEN = ''
$env:VERCEL_DEPLOYMENT_ID = ''
$env:VERCEL_TEAM_ID = ''
$env:SUPABASE_ACCESS_TOKEN = ''
$env:SUPABASE_PROJECT_REF = ''
$env:POSTGRES_HOST = ''
$env:POSTGRES_PORT = '5432'
$env:POSTGRES_DBNAME = ''
$env:POSTGRES_USER = ''
$env:POSTGRES_PASSWORD = ''
$env:STORAGE_MODE = 'disabled'
$env:STORAGE_SQLITE_FILE = 'work/data/reliability.sqlite3'
$env:STORAGE_DATABASE_URL = ''
$env:STORAGE_ALLOW_LOOPBACK = 'false'
Push-Location (Join-Path $ProjectRoot 'backend')
try {
    & $ProjectPython -m pytest --basetemp (Join-Path $ProjectWork 'pytest')
    if ($LASTEXITCODE -ne 0) { throw 'Tests failed.' }
    & $ProjectPython -m ruff check --config pyproject.toml . ..\scripts\smoke.py ..\scripts\browser-install.py ..\scripts\postgres-integration.py ..\scripts\storage-smoke.py ..\scripts\smoke_support.py ..\scripts\incident-smoke.py ..\scripts\retry-smoke.py
    if ($LASTEXITCODE -ne 0) { throw 'Lint checks failed.' }
    & $ProjectPython -m ruff format --check --config pyproject.toml . ..\scripts\smoke.py ..\scripts\browser-install.py ..\scripts\postgres-integration.py ..\scripts\storage-smoke.py ..\scripts\smoke_support.py ..\scripts\incident-smoke.py ..\scripts\retry-smoke.py
    if ($LASTEXITCODE -ne 0) { throw 'Formatting checks failed.' }
} finally { Pop-Location }
