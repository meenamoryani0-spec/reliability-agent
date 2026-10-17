. (Join-Path $PSScriptRoot 'environment.ps1')
$env:npm_config_cache = Join-Path $ProjectWork 'cache\npm'
$env:NODE_COMPILE_CACHE = Join-Path $ProjectWork 'cache\node'
$env:NEXT_TELEMETRY_DISABLED = '1'
$env:npm_config_update_notifier = 'false'
$FrontendRoot = Join-Path $ProjectRoot 'frontend'
$FrontendFsHelper = (Join-Path $PSScriptRoot 'frontend-fs.cjs').Replace('\', '/')
$FrontendNodeOptions = '--require="' + $FrontendFsHelper + '"'
if ($env:NODE_OPTIONS -notlike '*frontend-fs.cjs*') {
    $env:NODE_OPTIONS = ($env:NODE_OPTIONS + ' ' + $FrontendNodeOptions).Trim()
}
