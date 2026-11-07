# Thin wrapper: runs tools/smoke.py with the project's Python and passes arguments and exit code through.
# See docs/SMOKE.md. Container engine: CONTAINER_ENGINE, else Podman, else Docker (chosen by smoke.py).
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$script = Join-Path $PSScriptRoot 'smoke.py'

$python = $null
$venv = Join-Path $root '.venv\Scripts\python.exe'
if (Test-Path $venv) { $python = $venv }
foreach ($name in 'python', 'python3') {
    if (-not $python -and (Get-Command $name -ErrorAction SilentlyContinue)) { $python = $name }
}
if (-not $python) { Write-Host 'FAIL  python  - Python 3.11+ not found (create .venv or install Python)'; exit 2 }

& $python $script @args
exit $LASTEXITCODE
