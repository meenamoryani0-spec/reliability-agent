param([Parameter(Mandatory = $true)][string]$PythonExe)
. (Join-Path $PSScriptRoot 'environment.ps1')
if (-not (Test-Path -LiteralPath $PythonExe)) { throw 'PythonExe must point to an existing Python 3.12+ executable.' }
if (-not (Test-Path -LiteralPath $ProjectPython)) {
    & $PythonExe -m venv (Join-Path $ProjectRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed.' }
}
& $ProjectPython -m ensurepip --upgrade
if ($LASTEXITCODE -ne 0) { throw 'pip bootstrap failed.' }
& $ProjectPython -m pip install --require-hashes --disable-pip-version-check -r (Join-Path $ProjectRoot 'backend\requirements-dev.txt')
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
