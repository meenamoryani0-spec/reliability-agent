. (Join-Path $PSScriptRoot 'environment.ps1')
if (-not (Test-Path -LiteralPath $ProjectPython)) { throw 'Run scripts/setup.ps1 first.' }
Push-Location (Join-Path $ProjectRoot 'backend')
try {
    & $ProjectPython -m app.agent.smoke
    if ($LASTEXITCODE -ne 0) { throw 'Nebius connection is not verified; see the safe reason above.' }
} finally { Pop-Location }
