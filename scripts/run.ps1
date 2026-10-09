param([ValidateRange(1024, 65535)][int]$Port = 8000)
. (Join-Path $PSScriptRoot 'environment.ps1')
if (-not (Test-Path -LiteralPath $ProjectPython)) { throw 'Run scripts/setup.ps1 first.' }
Push-Location (Join-Path $ProjectRoot 'backend')
try {
    & $ProjectPython -m uvicorn app.main:app --host 127.0.0.1 --port $Port --no-access-log
    if ($LASTEXITCODE -ne 0) { throw 'Backend server exited with an error.' }
} finally { Pop-Location }
