. (Join-Path $PSScriptRoot 'environment.ps1')
if (-not (Test-Path -LiteralPath $ProjectPython)) { throw 'Run scripts/setup.ps1 first.' }
$env:ENVIRONMENT = 'test'
$env:LOG_LEVEL = 'INFO'
$env:N8N_MODE = 'disabled'
$env:N8N_BASE_URL = ''
$env:N8N_API_KEY = ''
$env:N8N_DNS_NAMESERVERS = '[]'
Push-Location (Join-Path $ProjectRoot 'backend')
try {
    & $ProjectPython -m pytest --basetemp (Join-Path $ProjectWork 'pytest')
    if ($LASTEXITCODE -ne 0) { throw 'Tests failed.' }
    & $ProjectPython -m ruff check --config pyproject.toml . ..\scripts\smoke.py ..\scripts\browser-install.py
    if ($LASTEXITCODE -ne 0) { throw 'Lint checks failed.' }
    & $ProjectPython -m ruff format --check --config pyproject.toml . ..\scripts\smoke.py ..\scripts\browser-install.py
    if ($LASTEXITCODE -ne 0) { throw 'Formatting checks failed.' }
} finally { Pop-Location }
