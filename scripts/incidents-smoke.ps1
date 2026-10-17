. (Join-Path $PSScriptRoot 'environment.ps1')
& $ProjectPython (Join-Path $PSScriptRoot 'incident-smoke.py')
if ($LASTEXITCODE -ne 0) { throw 'Incident creation/backend restart verification failed.' }
