<#
.SYNOPSIS
    Starts the whole Bee With Me stack on Windows: Postgres/PostGIS (Podman or Docker), the
    FastAPI backend, and the Vue frontend - instead of starting each one by hand.

    This script lives in the project root and uses its own location to find the
    project, so it works wherever the folder is copied to.

.PARAMETER ProjectPath
    Path to the bee-with-me project folder. Defaults to the folder this script
    is in.

.PARAMETER SkipContainers
    Don't start the database container (use this if it is already running). -SkipDocker still works.

.PARAMETER NoBrowser
    Don't auto-open the frontend in the default browser once it's up.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\start.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\start.ps1 -ProjectPath 'D:\bee-with-me'
#>

param(
    [string]$ProjectPath = $PSScriptRoot,
    [Alias('SkipDocker')]
    [switch]$SkipContainers,
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'

function Write-Step($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Warn($msg) { Write-Host $msg -ForegroundColor Yellow }

# Windows PowerShell 5.1 turns a native command's stderr into a terminating error under 'Stop' as soon
# as stderr is redirected (e.g. a podman warning on `info` with exit code 0 would abort the start).
# Native calls run through this with 'Continue' (local to the function); the script decides on $LASTEXITCODE.
function Invoke-Native([scriptblock]$Command) {
    $ErrorActionPreference = 'Continue'
    & $Command
}

# .env values: surrounding quotes, a trailing CR and an inline " # comment" are not part of the value;
# a leading `export ` (shell-style .env, lower case only, like python-dotenv) is accepted.
function Read-DotEnv([string]$Path) {
    $vars = @{}
    if (-not (Test-Path -LiteralPath $Path)) { return $vars }
    foreach ($line in Get-Content -LiteralPath $Path) {
        if ($line -cnotmatch '^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$') { continue }
        $key = $matches[1]
        $value = ($matches[2] -replace "`r$", '').Trim()
        if ($value -match '^"([^"]*)"') { $value = $matches[1] }
        elseif ($value -match "^'([^']*)'") { $value = $matches[1] }
        else { $value = ($value -replace '\s+#.*$', '').Trim() }
        $vars[$key] = $value
    }
    return $vars
}

# A folder path in one comparable form: / separators (repeated ones collapsed), no trailing /,
# WSL /mnt/<drive>/... as <drive>:/..., case-insensitive (Windows).
function ConvertTo-ComparablePath([string]$Path) {
    if (-not $Path) { return '' }
    $p = ($Path.Trim() -replace '\\', '/') -replace '/{2,}', '/'
    if ($p -match '^/mnt/([a-zA-Z])(/.*)?$') { $p = "$($matches[1]):$($matches[2])" }
    return $p.TrimEnd('/').ToLowerInvariant()
}

# Does the old compose-project-"docker" container belong to this folder? Its compose working_dir is
# <root>\docker or its data mount is <root>\data\pgdata. Missing information counts as "not ours".
function Test-OldContainerIsOurs([string]$Id) {
    $wd = (Invoke-Native { & $engine inspect --format '{{ index .Config.Labels `com.docker.compose.project.working_dir` }}' $Id 2>$null } | Out-String).Trim()
    $mnt = (Invoke-Native { & $engine inspect --format '{{range .Mounts}}{{if eq .Destination `/var/lib/postgresql/data`}}{{.Source}}{{end}}{{end}}' $Id 2>$null } | Out-String).Trim()
    if ($wd -eq '<no value>') { $wd = '' }
    $ours = ($wd -and (ConvertTo-ComparablePath $wd) -eq (ConvertTo-ComparablePath "$root\docker")) -or
            ($mnt -and (ConvertTo-ComparablePath $mnt) -eq (ConvertTo-ComparablePath "$root\data\pgdata"))
    return [pscustomobject]@{ Ours = [bool]$ours; WorkingDir = $wd; Mount = $mnt }
}

if (-not (Test-Path $ProjectPath)) {
    throw "Project folder not found: $ProjectPath`nPass the real location with -ProjectPath, e.g.:`n  powershell -ExecutionPolicy Bypass -File .\start.ps1 -ProjectPath 'C:\path\to\bee-with-me'"
}
# Resolve-Path keeps a trailing separator ('D:\bee-with-me\'); "$root\docker" must not get two.
$root = (Resolve-Path $ProjectPath).Path
if ($root -notmatch '^[A-Za-z]:\\\z') { $root = $root.TrimEnd('\', '/') }
Set-Location $root
Write-Step "Using project folder: $root"

# -- .env --------------------------------------------------------------------
if (-not (Test-Path "$root\.env")) {
    Write-Step 'No .env found - copying .env.example with a new random SECRET_KEY'
    # 48 random bytes, base64 (64 characters); never printed. New-Object/Create(): the static GetBytes(int)
    # needs .NET 6, Windows PowerShell 5.1 has .NET Framework.
    $keyBytes = New-Object byte[] 48
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($keyBytes) } finally { $rng.Dispose() }
    $newKey = [Convert]::ToBase64String($keyBytes)
    # The example's SECRET_KEY line gets the random value (a line that is not there is added); every other
    # line is copied as it is. An existing .env is never touched.
    $example = [IO.File]::ReadAllText("$root\.env.example")
    $keyLine = '(?im)^([ \t]*(?:export[ \t]+)?SECRET_KEY[ \t]*=)[^\r\n]*'
    if ($example -match $keyLine) {
        $example = [regex]::Replace($example, $keyLine, { param($m) $m.Groups[1].Value + $newKey })
    } else {
        if ($example -and -not $example.EndsWith("`n")) { $example += "`r`n" }
        $example += "SECRET_KEY=$newKey`r`n"
    }
    # The file is made empty under a temp name in the same folder, restricted to this user, filled and only
    # then moved into place: the key is never in a world-readable file and a half-written file is never
    # taken for the real one. Any failure removes the temp file and stops.
    $tmpEnv = "$root\.env.new-" + [guid]::NewGuid().ToString('N')
    $envMoved = $false
    try {
        [IO.File]::WriteAllBytes($tmpEnv, [byte[]]@())
        $mySid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
        icacls "$tmpEnv" /inheritance:r /grant:r "*${mySid}:F" | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "icacls could not restrict the new file to this user (exit code $LASTEXITCODE; a drive without ACLs, e.g. FAT/exFAT, cannot hold a private key file). Move the project to an NTFS folder, or create .env yourself from .env.example"
        }
        [IO.File]::WriteAllText($tmpEnv, $example, (New-Object Text.UTF8Encoding($false)))   # UTF-8 without BOM
        Move-Item -LiteralPath $tmpEnv -Destination "$root\.env" -ErrorAction Stop
        $envMoved = $true
    } catch {
        Remove-Variable newKey, keyBytes, example -ErrorAction SilentlyContinue
        throw "Could not create .env from .env.example: $($_.Exception.Message). Nothing was started and no .env was left behind."
    } finally {
        # Also runs on Ctrl+C or a stop between the write and the move: no temp copy of the key is left.
        if (-not $envMoved) { Remove-Item -LiteralPath $tmpEnv -Force -ErrorAction SilentlyContinue }
    }
    Remove-Variable newKey, keyBytes, example
    Write-Warn 'Edit .env with real values (POSTGRES_PASSWORD, HID_VENDOR_ID/HID_PRODUCT_ID, ...) before relying on this for anything but a quick test. SECRET_KEY was generated for you.'
}

# -- Database container (Podman first, Docker as the alternative) ----------------
$engine = if ($env:CONTAINER_ENGINE) { $env:CONTAINER_ENGINE }
          elseif (Get-Command podman -ErrorAction SilentlyContinue) { 'podman' }
          elseif (Get-Command docker -ErrorAction SilentlyContinue) { 'docker' }
          else { $null }

if (-not $SkipContainers) {
    if (-not $engine) {
        throw 'Neither podman nor docker was found on PATH. Install Podman (https://podman.io) or Docker, or re-run with -SkipContainers if the database is already running elsewhere.'
    }
    Invoke-Native { & $engine info *> $null }
    if ($LASTEXITCODE -ne 0) {
        if ($engine -eq 'podman') { throw 'Podman is installed but not running. Start it with: podman machine start' }
        throw 'Docker is installed but not running. Start Docker Desktop and re-run.'
    }

    # Podman on Windows runs in a WSL machine: named volume + host network for Postgres
    # (see docker\docker-compose.podman-machine.yaml for why).
    $composeFiles = @('-f', "$root\docker\docker-compose.yaml")
    if ($engine -eq 'podman') { $composeFiles += @('-f', "$root\docker\docker-compose.podman-machine.yaml") }

    # The override keeps Postgres in a named volume, so database files already in data\pgdata (bind mount of
    # the base file: Docker) would be left behind and the database would start empty.
    if ($composeFiles -match 'podman-machine' -and (Test-Path -LiteralPath "$root\data\pgdata\PG_VERSION")) {
        # Invariant culture: Get-Date -Format would use the current calendar (th-TH: Buddhist year).
        $stamp = (Get-Date).ToString('yyyyMMdd-HHmmss', [Globalization.CultureInfo]::InvariantCulture)
        throw ("This folder already has database files in data\pgdata (made with Docker), but Podman here would`n" +
               "start the database on its own named volume (bee-with-me_pgdata), which is empty: your data would look gone. Nothing was started.`n" +
               "To keep using data\pgdata, choose Docker:`n" +
               "  `$env:CONTAINER_ENGINE = 'docker'; powershell -ExecutionPolicy Bypass -File `"$root\start.ps1`"`n" +
               "To move to Podman instead (nothing is deleted):`n" +
               "(1) back up with Docker, not Podman (write down the dump file name it prints: step (4) restores that file), then stop the Docker stack:`n" +
               "  `$env:CONTAINER_ENGINE = 'docker'; powershell -ExecutionPolicy Bypass -File `"$root\scripts\backup.ps1`"`n" +
               "  docker compose -p bee-with-me -f `"$root\docker\docker-compose.yaml`" stop`n" +
               "(2) rename data\pgdata out of the way (it becomes $root\data\pgdata.docker-$stamp):`n" +
               "  Rename-Item -LiteralPath `"$root\data\pgdata`" -NewName `"pgdata.docker-$stamp`"`n" +
               "(3) start again with Podman (the Docker choice is cleared):`n" +
               "  Remove-Item Env:CONTAINER_ENGINE -ErrorAction SilentlyContinue; powershell -ExecutionPolicy Bypass -File `"$root\start.ps1`"`n" +
               "(4) stop the backend (Ctrl+C in that window), then restore the dump from step (1) (not a newer file: step (3) makes a dump of the empty Podman database):`n" +
               "  powershell -ExecutionPolicy Bypass -File `"$root\scripts\restore.ps1`" `"$root\data\backups\<the dump from step (1)>`"")
    }

    # data\backups is made now, by this user, before the database container starts (the same order as
    # start.sh, where rootful Docker would otherwise create data/ as root).
    # (Windows PowerShell 5.1 reports success for New-Item -Force below a plain file, so the folder is checked, not trusted.)
    $backupDir = "$root\data\backups"
    try {
        New-Item -ItemType Directory -Path $backupDir -Force -ErrorAction Stop | Out-Null
        if (-not (Test-Path -LiteralPath $backupDir -PathType Container)) { throw "$backupDir is not a folder." }
        $probe = Join-Path $backupDir (".write-test-" + [guid]::NewGuid().ToString('N'))
        [IO.File]::WriteAllBytes($probe, [byte[]]@())
        Remove-Item -LiteralPath $probe -Force
    } catch { throw "Cannot write to the backup folder $backupDir - not starting, so the database is never migrated without a backup. $($_.Exception.Message)" }

    # Upgrade from 1.7.1 or earlier: the stack ran as compose project "docker" (docker-db-1) on the
    # same port and, on the base file, the same data folder. Back that database up, then stop the old
    # project (no -v: data\pgdata stays and the new project reuses it), before the new one starts.
    # Only when that container belongs to THIS folder: another folder's copy or another app's "docker"
    # project is never stopped (see Test-OldContainerIsOurs).
    $oldDb = Invoke-Native { & $engine ps -q --filter 'label=com.docker.compose.project=docker' --filter 'label=com.docker.compose.service=db' } | Select-Object -First 1
    $oldDump = $null
    if ($oldDb) {
        $old = Test-OldContainerIsOurs $oldDb
        if (-not $old.Ours) {
            $wd = if ($old.WorkingDir) { $old.WorkingDir } else { 'unknown' }
            $mnt = if ($old.Mount) { $old.Mount } else { 'unknown' }
            throw ("A database container of compose project 'docker' (container $oldDb) is running, but it does not`n" +
                   "belong to this folder ($root): it is from another folder or another app`n" +
                   "(working_dir '$wd', data '$mnt'). It probably holds port 5432, so nothing was stopped and`n" +
                   "Bee With Me is not started. If it is an older Bee With Me install whose data you want here, back`n" +
                   "it up, stop it yourself, then start this one and restore the dump:`n" +
                   "  powershell -ExecutionPolicy Bypass -File `"$root\scripts\backup.ps1`" -Container $oldDb -OutDir `"$root\data\backups`"`n" +
                   "  $engine stop $oldDb`n" +
                   "  powershell -ExecutionPolicy Bypass -File `"$root\start.ps1`"`n" +
                   "  then, with the backend stopped: powershell -ExecutionPolicy Bypass -File `"$root\scripts\restore.ps1`" `"$root\data\backups\<the new dump>`"`n" +
                   "Otherwise stop that app (or move one of them to another port) and start again.")
        }
        Write-Step "Found the database of an older install (compose project 'docker', container $oldDb): backing it up, then stopping it"
        try { & "$root\scripts\backup.ps1" -OutDir "$root\data\backups" -Container $oldDb }
        catch { throw 'Backup of the old database failed - not continuing; the old install is left running.' + " $($_.Exception.Message)" }
        $oldDump = Join-Path "$root\data\backups" ((Get-Content "$root\data\backups\last-backup.json" -Raw | ConvertFrom-Json).dump)
        Invoke-Native { & $engine compose -p docker -f "$root\docker\docker-compose.yaml" down }
        if ($LASTEXITCODE -ne 0) { throw "$engine compose -p docker down failed - stop the old containers (docker-db-1, docker-tiles-1) yourself, then re-run." }
    }

    Write-Step "Starting database ($engine compose -p bee-with-me up -d)"
    Invoke-Native { & $engine compose -p bee-with-me @composeFiles up -d }
    if ($LASTEXITCODE -ne 0) { throw "$engine compose -p bee-with-me up failed - see the output above." }

    Write-Step 'Waiting for Postgres to accept connections'
    $pgPort = (Read-DotEnv "$root\.env")['POSTGRES_PORT']
    if ($pgPort -notmatch '^\d+\z') { $pgPort = '5432' }

    $deadline = (Get-Date).AddSeconds(60)
    $ready = $false
    do {
        $ready = (Test-NetConnection -ComputerName 'localhost' -Port $pgPort -InformationLevel Quiet -WarningAction SilentlyContinue)
        if (-not $ready) { Start-Sleep -Seconds 1 }
    } until ($ready -or (Get-Date) -gt $deadline)

    if (-not $ready) {
        Write-Warn "Postgres didn't come up on port $pgPort within 60s - continuing anyway. Check: $engine compose -f docker\docker-compose.yaml -p bee-with-me logs"
    }

    if ($oldDump -and $engine -eq 'podman') {
        # With the podman-machine override the old data is in the volume docker_pgdata, not data\pgdata:
        # the new database (volume bee-with-me_pgdata) is empty. Don't start the backend on it.
        throw ("The old install kept its data in the Podman volume docker_pgdata; the new database " +
               "(volume bee-with-me_pgdata) starts empty, so the backend is not started. Restore the " +
               "backup just taken into it, then start again:`n" +
               "  powershell -ExecutionPolicy Bypass -File `"$root\scripts\restore.ps1`" `"$oldDump`"`n" +
               "  powershell -ExecutionPolicy Bypass -File `"$root\start.ps1`"`n" +
               "(The volume docker_pgdata is left as it was.)")
    }
}

# -- Python venv + backend deps -----------------------------------------------
$venvActivate = "$root\.venv\Scripts\Activate.ps1"
if (-not (Test-Path $venvActivate)) {
    Write-Step 'Creating Python virtual environment (.venv)'
    $py = if (Get-Command python -ErrorAction SilentlyContinue) { 'python' }
          elseif (Get-Command py -ErrorAction SilentlyContinue) { 'py' }
          else { throw 'Python was not found on PATH (tried "python" and "py"). Install Python 3.11+ from python.org and re-run.' }
    & $py -m venv "$root\.venv"
    if (-not (Test-Path $venvActivate)) {
        throw "Failed to create the virtual environment at $root\.venv - if 'python' opened the Microsoft Store instead of actually running, that's the Windows app-execution-alias stub, not real Python. Install Python 3.11+ from https://python.org (check 'Add python.exe to PATH' during install), or disable the stub under Settings > Apps > Advanced app settings > App execution aliases, then re-run this script."
    }
}

Write-Step 'Installing/checking backend dependencies'
Invoke-Native { & "$root\.venv\Scripts\python.exe" -m pip install -q -r "$root\backend\requirements.txt" }
if ($LASTEXITCODE -ne 0) {
    # Offline laptops still start with what is installed; a missing package shows up when the backend starts.
    Write-Warn "pip install failed (exit $LASTEXITCODE; offline?) - continuing with the packages already in .venv."
}

# -- Database migrations: back up first if any are pending ---------------------
if (-not $SkipContainers) {
    Write-Step 'Checking database migrations'
    # Exit 3 means Postgres isn't accepting connections yet (slow after a reboot or
    # `podman machine start`): retry for up to 90 s rather than let the backend migrate later
    # without the backup this check exists for. Any other code is final at once.
    $migDeadline = (Get-Date).AddSeconds(90)
    # BWM_MIGRATE_WAIT_S: shorter deadline for the script tests (backend/tests/test_scripts_behaviour.py)
    if ($env:BWM_MIGRATE_WAIT_S -match '^\d+\z') { $migDeadline = (Get-Date).AddSeconds([int]$env:BWM_MIGRATE_WAIT_S) }
    while ($true) {
        Invoke-Native { & "$root\.venv\Scripts\python.exe" -m backend.db.migrate status }
        $migExit = $LASTEXITCODE
        if ($migExit -ne 3 -or (Get-Date) -gt $migDeadline) { break }
        Write-Warn 'Database not reachable yet - retrying in 3 s'
        Start-Sleep -Seconds 3
    }
    switch ($migExit) {
        0  { }
        10 {
            Write-Step 'Migrations pending - taking a backup first (data\backups)'
            try { & "$root\scripts\backup.ps1" -OutDir "$root\data\backups" }
            catch { throw 'Backup failed - not starting, so the database is never migrated without a backup.' + " $($_.Exception.Message)" }
        }
        1  { throw 'Not starting: the migration files are invalid: see the message above.' }
        2  { throw 'The database is newer than this version of Bee With Me. Update the app (git pull) instead of starting an older one.' }
        default { throw "Could not check database migrations (database not reachable?) - not starting, so the database is never migrated without a backup. Check: $engine compose -f docker\docker-compose.yaml -p bee-with-me logs" }
    }
}

# BWM_START_DRY_RUN=1 (script tests): stop after the database and migration decisions.
if ($env:BWM_START_DRY_RUN -eq '1') {
    Write-Host 'DRY RUN: would start backend and frontend'
    exit 0
}

# -- Frontend deps -------------------------------------------------------------
if (-not (Get-Command node -ErrorAction SilentlyContinue) -or -not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw 'Node.js was not found on PATH. Install Node.js 24 LTS and re-run.'
}
# Floor matches "engines" in frontend\package.json; .npmrc engine-strict enforces it for npm too.
$nodeVersion = [version]((node -v).TrimStart('v'))
if ($nodeVersion -lt [version]'22.12.0') {
    throw "Node.js $nodeVersion is too old (need 22.12+). Install Node.js 24 LTS and re-run."
}
if (-not (Test-Path "$root\frontend\node_modules")) {
    Write-Step 'Installing frontend dependencies (first run only - this can take a minute)'
    Push-Location "$root\frontend"
    npm install
    Pop-Location
}

# -- Backend (own window) ------------------------------------------------------
Write-Step 'Starting backend (uvicorn) in a new window'
Start-Process powershell -ArgumentList @(
    '-NoExit', '-ExecutionPolicy', 'Bypass', '-Command',
    "Set-Location '$root'; & '$venvActivate'; uvicorn backend.main:app"
) -WindowStyle Normal

# -- Frontend (own window) ------------------------------------------------------
Write-Step 'Starting frontend (vite) in a new window'
Start-Process powershell -ArgumentList @(
    '-NoExit', '-ExecutionPolicy', 'Bypass', '-Command',
    "Set-Location '$root\frontend'; npm run dev"
) -WindowStyle Normal

Start-Sleep -Seconds 2
if (-not $NoBrowser) { Start-Process 'http://localhost:5173' }

Write-Host ''
Write-Host 'Bee With Me is starting up:' -ForegroundColor Green
Write-Host '  Backend:  http://localhost:8000  (API docs at /docs)'
Write-Host '  Frontend: http://localhost:5173'
Write-Host ''
Write-Host 'Backend and frontend run in their own windows - close a window (or Ctrl+C inside it) to stop that service.' -ForegroundColor Gray
$engineHint = if ($engine) { $engine } else { 'podman' }
Write-Host 'The database keeps running in its container until you stop it yourself:' -ForegroundColor Gray
Write-Host "  $engineHint compose -p bee-with-me -f docker\docker-compose.yaml down" -ForegroundColor Gray
