param([switch]$UseArchiveFallback)
. (Join-Path $PSScriptRoot 'environment.ps1')
if (-not (Test-Path -LiteralPath $ProjectPython)) { throw 'Run scripts/setup.ps1 first.' }
if ($UseArchiveFallback) {
    & $ProjectPython (Join-Path $PSScriptRoot 'browser-install.py')
} else {
    & $ProjectPython -m playwright install chromium --only-shell
}
if ($LASTEXITCODE -ne 0) { throw 'Chromium installation failed.' }
