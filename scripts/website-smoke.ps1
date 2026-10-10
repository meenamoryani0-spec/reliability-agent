param([Parameter(Mandatory = $true)][string]$TargetId)
. (Join-Path $PSScriptRoot 'environment.ps1')
if (-not (Test-Path -LiteralPath $ProjectPython)) { throw 'Run scripts/setup.ps1 first.' }
Push-Location (Join-Path $ProjectRoot 'backend')
try {
    & $ProjectPython -m app.tools.smoke $TargetId
    if ($LASTEXITCODE -ne 0) { throw 'Website checks need attention; see the normalized results above.' }
} finally { Pop-Location }
