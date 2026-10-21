<#
.SYNOPSIS
    Prepares this laptop to start Bee With Me without internet (B62). Run it at home, with internet,
    after installing or updating the app.

.DESCRIPTION
    1. Downloads every backend package (and its dependencies) for this laptop's Python into vendor\wheels
       (wheels only) and records their SHA-256 in vendor\wheels\SHA256SUMS.
       start.ps1 installs from there when a package is missing and there is no internet.
    2. Installs the backend packages into .venv from that folder.
    3. Installs the frontend packages (npm ci), which also fills the local npm cache.

    vendor\ is not committed to git. Run again after every update that changes backend\requirements.txt
    or frontend\package-lock.json.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\prepare-offline.ps1
#>
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$python = "$root\.venv\Scripts\python.exe"
$wheels = "$root\vendor\wheels"
$requirements = "$root\backend\requirements.txt"

# Same Node.js rule as start.ps1, checked before anything is downloaded or vendor\wheels is emptied.
if (-not (Get-Command node -ErrorAction SilentlyContinue) -or -not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw 'Node.js was not found on PATH. Install Node.js 24 LTS and re-run.'
}
$nodeVersion = [version]((node -v).TrimStart('v'))
if ($nodeVersion -lt [version]'22.12.0') {
    throw "Node.js $nodeVersion is too old (need 22.12+). Install Node.js 24 LTS and re-run."
}
if ($nodeVersion.Major -eq 23 -or $nodeVersion.Major -eq 25) {
    throw "Node.js $nodeVersion is not supported by the frontend tools (use 22.12+, 24 or 26+). Install Node.js 24 LTS and re-run."
}

if (-not (Test-Path -LiteralPath $python)) {
    $py = if (Get-Command python -ErrorAction SilentlyContinue) { 'python' }
          elseif (Get-Command py -ErrorAction SilentlyContinue) { 'py' }
          else { throw 'Python was not found on PATH (tried "python" and "py"). Install Python 3.11+ from python.org and re-run.' }
    Write-Host '==> Creating Python virtual environment (.venv)' -ForegroundColor Cyan
    & $py -m venv "$root\.venv"
    if ($LASTEXITCODE -ne 0) { throw 'Could not create .venv.' }
}

Write-Host "==> Downloading backend packages into $wheels" -ForegroundColor Cyan
# Start from an empty folder, so no old or foreign wheel stays next to the fresh ones. Wheels only: a source
# archive would run its own build code during the install.
if (Test-Path -LiteralPath $wheels) { Remove-Item -LiteralPath $wheels -Recurse -Force }
New-Item -ItemType Directory -Force -Path $wheels | Out-Null
& $python -m pip download --only-binary :all: -r $requirements -d $wheels
if ($LASTEXITCODE -ne 0) { throw 'pip download failed - is the internet up?' }
# Record every wheel's SHA-256: start.ps1 uses the folder only while it still matches (scripts\wheelhouse.py).
& $python "$root\scripts\wheelhouse.py" write $wheels
if ($LASTEXITCODE -ne 0) { throw 'Could not write vendor\wheels\SHA256SUMS.' }

Write-Host '==> Installing backend packages from vendor\wheels' -ForegroundColor Cyan
& $python -m pip install --no-index --find-links $wheels -r $requirements
if ($LASTEXITCODE -ne 0) { throw 'Installing from vendor\wheels failed - see the messages above.' }

Write-Host '==> Installing frontend packages (npm ci)' -ForegroundColor Cyan
Push-Location "$root\frontend"
try {
    npm ci --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { throw 'npm ci failed - is the internet up?' }
} finally { Pop-Location }
# The start script skips its own npm ci only while this marker matches the lock file (start.ps1, B62).
$lockHash = (Get-FileHash -LiteralPath "$root\frontend\package-lock.json" -Algorithm SHA256).Hash
Set-Content -LiteralPath "$root\frontend\node_modules\.bwm-package-lock.sha256" -Value $lockHash -Encoding ascii

Write-Host 'Done. This laptop can now start Bee With Me without internet.' -ForegroundColor Green
