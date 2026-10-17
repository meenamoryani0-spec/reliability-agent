. (Join-Path $PSScriptRoot 'environment.ps1')
& $ProjectPython (Join-Path $PSScriptRoot 'storage-smoke.py')
if ($LASTEXITCODE -ne 0) { throw 'Storage/backend restart verification failed.' }
