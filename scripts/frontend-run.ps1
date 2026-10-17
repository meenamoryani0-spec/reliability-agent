param([int]$Port = 3000, [switch]$Release)
. (Join-Path $PSScriptRoot 'frontend-environment.ps1')
if ($Port -lt 1024 -or $Port -gt 65535) { throw 'Use a port between 1024 and 65535.' }
Push-Location $FrontendRoot
try {
    if ($Release) { npm run start -- --port $Port }
    else { npm run dev -- --port $Port }
    if ($LASTEXITCODE -ne 0) { throw 'Frontend exited with an error.' }
} finally { Pop-Location }
