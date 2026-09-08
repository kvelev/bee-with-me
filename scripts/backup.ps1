<#
.SYNOPSIS
    Dumps the Bee With Me database to a timestamped file.

    Run it after every operation, and on a schedule between them. The whole record of a
    callout lives in one Docker volume on one laptop; this is the only thing standing
    between a disk failure and losing it.

.PARAMETER OutDir
    Where to write the dump. Point this at a USB stick or a second drive — a backup on
    the same disk as the database is not a backup.

.PARAMETER Keep
    How many dumps to retain in OutDir (oldest are pruned). Default 30.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\backup.ps1 -OutDir E:\bee-backups
#>

param(
    [string]$OutDir = (Join-Path $env:USERPROFILE 'Desktop\bee-backups'),
    [int]$Keep = 30
)

$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent

# Read DB settings out of .env so this never drifts from the running config
$envVars = @{}
foreach ($line in Get-Content (Join-Path $root '.env')) {
    if ($line -match '^\s*([A-Z_]+)\s*=\s*(.*?)\s*$') { $envVars[$matches[1]] = $matches[2] }
}
$db   = if ($envVars['POSTGRES_DB'])   { $envVars['POSTGRES_DB'] }   else { 'rescuer_locator' }
$user = if ($envVars['POSTGRES_USER']) { $envVars['POSTGRES_USER'] } else { 'rescuer' }

if (-not (Test-Path $OutDir)) { New-Item -ItemType Directory -Path $OutDir -Force | Out-Null }

$stamp  = Get-Date -Format 'yyyy-MM-dd_HHmmss'
$target = Join-Path $OutDir "beewithme_$stamp.sql"

$container = (docker compose -f (Join-Path $root 'docker\docker-compose.yaml') ps -q db)
if (-not $container) { throw 'Database container is not running — start it with: docker compose up -d' }

Write-Host "==> Dumping $db to $target" -ForegroundColor Cyan
docker exec $container pg_dump -U $user -d $db | Out-File -FilePath $target -Encoding utf8

$size = [math]::Round((Get-Item $target).Length / 1MB, 2)
if ((Get-Item $target).Length -eq 0) { throw "Dump is empty — check the container logs" }
Write-Host "==> Wrote $size MB" -ForegroundColor Green

# Prune old dumps
Get-ChildItem $OutDir -Filter 'beewithme_*.sql' |
    Sort-Object LastWriteTime -Descending |
    Select-Object -Skip $Keep |
    ForEach-Object { Write-Host "    pruning $($_.Name)"; Remove-Item $_.FullName }

Write-Host ''
Write-Host 'To restore into a running (empty) database:' -ForegroundColor Gray
Write-Host "  Get-Content '$target' | docker exec -i <container> psql -U $user -d $db" -ForegroundColor Gray
