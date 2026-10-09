. (Join-Path $PSScriptRoot 'environment.ps1')
& $ProjectPython (Join-Path $PSScriptRoot 'smoke.py')
if ($LASTEXITCODE -ne 0) { throw 'Live HTTP smoke test failed.' }
