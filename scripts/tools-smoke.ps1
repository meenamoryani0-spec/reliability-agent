. (Join-Path $PSScriptRoot 'environment.ps1')
Push-Location (Join-Path $ProjectRoot 'backend')
try {
    & $ProjectPython -m app.agent.tool_smoke
    if ($LASTEXITCODE -ne 0) { throw 'Registry fixture smoke test failed.' }
} finally { Pop-Location }
& $ProjectPython (Join-Path $PSScriptRoot 'smoke.py')
if ($LASTEXITCODE -ne 0) { throw 'Tool catalog HTTP smoke test failed.' }
