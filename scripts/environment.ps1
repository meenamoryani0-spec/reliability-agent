$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ProjectWork = Join-Path $ProjectRoot 'work'
New-Item -ItemType Directory -Force -Path $ProjectWork | Out-Null
$env:UV_CACHE_DIR = Join-Path $ProjectWork 'cache\uv'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $ProjectWork 'python'
$env:PIP_CACHE_DIR = Join-Path $ProjectWork 'cache\pip'
$env:PYTHONPYCACHEPREFIX = Join-Path $ProjectWork 'cache\pycache'
$env:TEMP = Join-Path $ProjectWork 'tmp'
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Force -Path $env:UV_CACHE_DIR, $env:UV_PYTHON_INSTALL_DIR, $env:PIP_CACHE_DIR, $env:PYTHONPYCACHEPREFIX, $env:TEMP | Out-Null
$ProjectPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
