. (Join-Path $PSScriptRoot 'environment.ps1')
& $ProjectPython (Join-Path $PSScriptRoot 'smoke.py') --agent
if ($LASTEXITCODE -ne 0) { throw 'Investigation fixture HTTP smoke test failed.' }
