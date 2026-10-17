. (Join-Path $PSScriptRoot 'environment.ps1')
& $ProjectPython (Join-Path $PSScriptRoot 'retry-smoke.py')
if ($LASTEXITCODE -ne 0) { throw 'Approved retry/operator restart verification failed.' }
