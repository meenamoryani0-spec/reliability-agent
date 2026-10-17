. (Join-Path $PSScriptRoot 'environment.ps1')
& $ProjectPython (Join-Path $PSScriptRoot 'smoke.py') --infrastructure
if ($LASTEXITCODE -ne 0) { throw 'Live backend/synthetic infrastructure smoke test failed.' }
