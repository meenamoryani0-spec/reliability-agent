. (Join-Path $PSScriptRoot 'frontend-environment.ps1')
& $ProjectPython (Join-Path $PSScriptRoot 'deployment-smoke.py')
if ($LASTEXITCODE -ne 0) { throw 'Local production-mode HTTP smoke failed.' }
