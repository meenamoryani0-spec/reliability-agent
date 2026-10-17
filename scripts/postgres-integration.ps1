param([string]$BinDir = '', [string]$TemplateDir = '')
. (Join-Path $PSScriptRoot 'environment.ps1')
if (-not $BinDir) { $BinDir = Join-Path $ProjectWork 'postgres-runtime\pgsql\bin' }
$PostgresTemplateArgs = @()
if ($TemplateDir) { $PostgresTemplateArgs = @('--template-dir', $TemplateDir) }
& $ProjectPython (Join-Path $PSScriptRoot 'postgres-integration.py') --bin-dir $BinDir --powershell (Get-Process -Id $PID).Path @PostgresTemplateArgs
if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL integration tests failed.' }
