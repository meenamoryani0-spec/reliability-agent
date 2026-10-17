. (Join-Path $PSScriptRoot 'frontend-environment.ps1')
Push-Location $FrontendRoot
try {
    npm ci --no-fund
    if ($LASTEXITCODE -ne 0) { throw 'Frontend installation failed.' }
} finally { Pop-Location }
