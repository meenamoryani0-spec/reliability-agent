. (Join-Path $PSScriptRoot 'frontend-environment.ps1')
Push-Location $FrontendRoot
try {
    foreach ($task in @('test', 'lint', 'build', 'typecheck')) {
        npm run $task
        if ($LASTEXITCODE -ne 0) { throw "Frontend $task failed." }
    }
    npm audit --omit=dev --audit-level=moderate
    if ($LASTEXITCODE -ne 0) { throw 'Frontend runtime dependency audit failed.' }
} finally { Pop-Location }
