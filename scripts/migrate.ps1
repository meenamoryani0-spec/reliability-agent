param([ValidateSet('upgrade', 'status')][string]$Action = 'status')
. (Join-Path $PSScriptRoot 'environment.ps1')
Push-Location (Join-Path $ProjectRoot 'backend')
try {
    & $ProjectPython -m app.db.cli $Action
    if ($LASTEXITCODE -ne 0) { throw 'Application database is not verified.' }
} finally { Pop-Location }
