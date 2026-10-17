. (Join-Path $PSScriptRoot 'environment.ps1')
& $ProjectPython (Join-Path $PSScriptRoot 'recovery-smoke.py')
if ($LASTEXITCODE -ne 0) { throw 'Recovery smoke verification failed.' }
