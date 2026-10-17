param([int]$Port = 3000)
. (Join-Path $PSScriptRoot 'frontend-environment.ps1')
& $ProjectPython (Join-Path $PSScriptRoot 'frontend-demo.py') --port $Port
if ($LASTEXITCODE -ne 0) { throw 'Synthetic preview failed.' }
