. (Join-Path $PSScriptRoot 'frontend-environment.ps1')
& $ProjectPython (Join-Path $PSScriptRoot 'frontend-smoke.py')
if ($LASTEXITCODE -ne 0) { throw 'Frontend HTTP/browser smoke failed.' }
