. (Join-Path $PSScriptRoot 'environment.ps1')
& $ProjectPython (Join-Path $PSScriptRoot 'smoke.py') --browser
if ($LASTEXITCODE -ne 0) { throw 'Live browser/backend smoke test failed.' }
