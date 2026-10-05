# Bee With Me

[![CI](https://github.com/kvelev/bee-with-me/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/kvelev/bee-with-me/actions/workflows/ci.yml?query=branch%3Amain)
[![Release](https://img.shields.io/github/v/release/kvelev/bee-with-me?sort=semver)](https://github.com/kvelev/bee-with-me/releases/latest)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
![Python 3.11](https://img.shields.io/badge/python-3.11-3776AB?logo=python&logoColor=white)
![Node 22 | 24](https://img.shields.io/badge/node-22%20%7C%2024-5FA04E?logo=nodedotjs&logoColor=white)
![PostGIS 16-3.4](https://img.shields.io/badge/PostGIS-16--3.4-336791?logo=postgresql&logoColor=white)

Offline people-tracking application for LoRaWAN-based rescue and volunteer operations. RescuerBee devices transmit MGRS coordinates over a USB LoRaWAN gateway; the backend parses the frames, stores positions in PostGIS, and broadcasts them in real time to a bilingual (EN/BG) web interface showing live positions on an interactive map.

> This is an intranet-only application. It is not designed to be exposed to the internet and makes security trade-offs accordingly.

---

## Features

- **Live map** — OpenLayers map with real-time MGRS position markers updated via WebSocket. Supports Street, Dark, Satellite, Topo and BG Mountains basemaps.
- **MGRS grid overlay** — toggleable graticule with labels that scale precision with zoom level.
- **Stale indicator** — markers grey out automatically after 10 minutes without a new frame.
- **SOS alerts** — pulsing red marker, audio alarm and toast notification when a device activates SOS. Alerts persist across page refreshes until manually resolved.
- **Distance / bearing tool** — click two points on the map to measure distance (km) and bearing (°).
- **Volunteers** — manage field personnel with name, rank, blood type, phone, PIN, photo and team memberships.
- **Bulk import** — import volunteers from an XLS spreadsheet (Bulgarian or English column headers).
- **Teams** — group volunteers into colour-coded teams; each team can have a designated leader.
- **Devices** — register RescuerBee devices by serial number and assign them to volunteers.
- **Export** — export location history to CSV, GeoJSON or PDF report with date/person/team filters.
- **JWT authentication** — long-lived access tokens (intranet deployment) with silent refresh via 7-day refresh tokens.

---

## Prerequisites

- Python 3.11+
- Node.js 22.12+ (24 LTS recommended; `frontend/.nvmrc`)
- Podman 4.7+ with a compose provider (`podman compose`), **or** Docker with Docker Compose

---

## Setup

### 1. Environment

```bash
cp .env.example .env
```

Edit `.env`:

```env
POSTGRES_PASSWORD=your_password
SECRET_KEY=a_long_random_string   # used for JWT signing
SERIAL_PORT=/dev/ttyUSB0          # USB path of the LoRaWAN serial gateway
SERIAL_BAUD=9600
HID_VENDOR_ID=0x0ACD              # USB HID gateway VID (hex)
HID_PRODUCT_ID=0xFAAF             # USB HID gateway PID (hex)
REFRESH_TOKEN_EXPIRE_DAYS=7
```

### 2. Database

```bash
podman compose -p bee-with-me -f docker/docker-compose.yaml up -d
```

(Docker: `docker compose -p bee-with-me -f docker/docker-compose.yaml up -d`)

Podman on Windows/macOS also needs the `docker-compose.podman-machine.yaml` override — see
"Podman on Windows/macOS (podman machine)" below.

The backend creates and upgrades the schema itself on start-up: numbered files in
`backend/db/migrations/` are applied in order and recorded in the `schema_migrations` table.
Check the state at any time with:

```bash
python -m backend.db.migrate status   # exit 0 = up to date, 10 = pending, 2 = database is newer than the app, 3 = database not reachable, 1 = invalid migration files / failed migration
```

Every migration file runs under a lock timeout (`MIGRATION_LOCK_TIMEOUT`, default `5s`, form `200ms`, `5s` or
`1min`): if another session holds a lock on a table the file needs, the start-up fails with a clear
error naming the file instead of hanging. Nothing is changed; stop the backend and other tools using
the database, then start again.

The start scripts retry only exit 3 (Postgres still starting) for up to 90 s; exit 1 and 2 refuse at once.

The start scripts take a backup (`data/backups/`) before applying pending migrations, and refuse to
start when they cannot check the database for 90 s. `-SkipContainers` (start.ps1) / `--skip-containers`
(start.sh) also skips this check and the automatic pre-migration backup — take one manually with
`scripts/backup.ps1` / `scripts/backup.sh` first.

The backend itself also refuses to apply pending migrations to a database that already holds data
unless a backup of *that* database was taken first: every backup writes `last-backup.json` next to the
dump (server `system_identifier`, applied migrations, dump name, time), and the backend migrates only
when `data/backups/last-backup.json` (setting `BACKUP_MARKER_PATH`) is of the same server, in the
current migration state, and less than 24 h old. A fresh, empty database needs no backup. A refusal
changes nothing; run the start script (or `scripts/backup.ps1 -OutDir data\backups` /
`./scripts/backup.sh data/backups`) and start again. The start scripts run uvicorn without `--reload`,
so a `git pull` never migrates a running field install behind your back. Developers who want hot
reload start uvicorn by hand with `ALLOW_MIGRATE_WITHOUT_BACKUP=true` — on development data only:

```powershell
$env:ALLOW_MIGRATE_WITHOUT_BACKUP='true'; uvicorn backend.main:app --reload
```

```bash
ALLOW_MIGRATE_WITHOUT_BACKUP=true uvicorn backend.main:app --reload
```

To reset to an empty database (**destroys all data**): stop the backend, run
`podman compose -p bee-with-me -f docker/docker-compose.yaml down` (Docker: `docker compose -p bee-with-me -f docker/docker-compose.yaml down`),
delete the `data/pgdata` folder (it is a bind mount, `down -v` does not remove it), then
`podman compose -p bee-with-me -f docker/docker-compose.yaml up -d` (Docker: `docker compose -p bee-with-me -f docker/docker-compose.yaml up -d`).

**Coming back after a reboot.** `restart: unless-stopped` only helps while the container engine runs:
- Podman on Windows/macOS: `podman machine start` (once per boot), then `podman compose -p bee-with-me -f docker/docker-compose.yaml -f docker/docker-compose.podman-machine.yaml up -d` or the start script.
- Podman on Linux (rootless): `systemctl --user enable --now podman-restart.service` restarts
  `unless-stopped` containers at login; for start at boot without login also run `loginctl enable-linger $USER`.
- Docker: Docker Desktop / the docker service restarts the container by itself.

The start scripts use Podman when it is installed and Docker otherwise; set `CONTAINER_ENGINE=docker`
(or `podman`) to choose explicitly.

The compose project is named `bee-with-me` (containers `bee-with-me-db-1`, `bee-with-me-tiles-1`), so
the scripts only ever pick this project's database; with the Podman-machine override the data volume
is `bee-with-me_pgdata`. Every script passes `-p bee-with-me` to compose explicitly (older
podman-compose versions ignore the `name:` key).

**Upgrading from 1.7.1 or earlier.** Older versions ran as compose project `docker` (containers
`docker-db-1`, `docker-tiles-1`) on the same ports, so the new project could not start next to them.
The start scripts handle this once: when a running `docker-db-1` (project `docker`, service `db`) is
found, they back it up into `data/backups` (`scripts/backup.ps1 -Container <id>` /
`scripts/backup.sh --container <id>`), refuse to continue if that backup fails, then run
`podman compose -p docker -f docker/docker-compose.yaml down` (Docker: `docker compose -p docker …`;
no `-v`, nothing is deleted) and start `bee-with-me`. On the base file the data stays in `data/pgdata`
and the new project reuses it. With the Podman-machine override the old data is in the volume
`docker_pgdata` and the new volume `bee-with-me_pgdata` starts empty: the start script stops before
the backend and prints the restore command for the backup it just took
(`scripts/restore.ps1 '<dump>'` / `./scripts/restore.sh <dump>`); run it, then start again. The old
volume is left in place until you remove it yourself.
This happens only when the old container belongs to **this folder**: its compose `working_dir` label
is `<this folder>/docker` or its data mount is `<this folder>/data/pgdata` (compared without regard to
`\` vs `/`, a trailing slash, letter case on Windows, or the WSL `/mnt/<drive>/…` form). A project
`docker` from another folder (for example a copy of the app installed elsewhere) or from another app
is never backed up or stopped: the start script stops instead and prints the backup command
(`-Container <id>` / `--container <id>`), the stop command and the restore command to move that data
here yourself.

**Podman on Windows/macOS (podman machine).** Start the database with the extra override file:
`podman compose -p bee-with-me -f docker/docker-compose.yaml -f docker/docker-compose.podman-machine.yaml up -d`
(the start scripts do this automatically). It keeps the Postgres data in a named volume inside the
Podman VM — Postgres can't set permissions on a Windows-drive folder — and puts Postgres on the VM's
host network so `localhost:5432` reaches it from Windows. **The data then lives in the VM: `podman
machine rm` or a reset deletes it — back up with `scripts/backup.ps1` onto another disk.**
To reset to an empty database in this mode,
`podman compose -p bee-with-me -f docker/docker-compose.yaml -f docker/docker-compose.podman-machine.yaml down -v`
removes the named volume instead of deleting `data/pgdata`.

The database only listens on localhost (`127.0.0.1`, in both modes; the tile server too) — the
backend, the hardware reader and the scripts all run on this machine. To reach it from another
machine, change the binding in the compose files deliberately (and set a real `POSTGRES_PASSWORD`;
the backend logs an INSECURE CONFIG line while it is still `change_me`).

Schema changes: add a new numbered file; never edit a file that has already been applied.

#### Backup and restore

Back up with `scripts/backup.ps1 -OutDir E:\bee-backups` (Windows) or `./scripts/backup.sh /media/usb/bee-backups`
(Linux/macOS) — onto another disk. Both find the database container (`bee-with-me-db-1`) through the
chosen engine: Podman first, Docker when Podman is not installed (`CONTAINER_ENGINE=docker` to force it).
They read `POSTGRES_DB` / `POSTGRES_USER` from the environment first, then from `.env` (like the backend).
These parsing notes apply to the scripts only (the backend reads `.env` through its own settings): in the
scripts, an environment variable set to an empty string counts as unset (the `.env` value or the default is
used), `.env` keys match in any case (`postgres_db=` works too), and a leading `export ` is accepted in
lower case only, like python-dotenv (an `EXPORT KEY=` line is ignored). `-Keep` / `KEEP` must be at least 1;
the dump just written is never pruned. An empty `-OutDir ''` / `""` writes to `backups` in the project
folder. Restore refuses the system databases `postgres`, `template0`, `template1` and `template_postgis`.

Dumps hold every name and position of a callout. `backup.ps1` restricts the dump folder to the current
user (by SID, no inherited permissions) when it creates the folder, and also when it finds an existing
folder that still inherits its permissions and holds nothing but dumps; any other existing folder is
left as it is, with a warning. FAT/exFAT USB sticks have no ACLs at all: there the dumps are readable by
anyone who has the stick, so keep it with you. `backup.sh` makes the dumps `600` (not enforced under
Git Bash on NTFS — use `backup.ps1` on Windows).

**Restore only dumps you made yourself and kept on trusted media.** `pg_restore` runs as the database
superuser inside the container, so a crafted dump can do anything the database server can.

To restore a dump (**replaces the whole database**): stop the backend first (close its window / Ctrl+C), then

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\restore.ps1 'E:\bee-backups\beewithme_2026-10-02_101500.dump'
```

```bash
./scripts/restore.sh /media/usb/bee-backups/beewithme_2026-10-02_101500.dump
```

The restore script first checks the dump (`pg_restore -l`) and refuses before touching any database if
it cannot be read. It then restores into a side database `<db>_restore_<suffix>` in one transaction that
stops at the first error (`pg_restore --exit-on-error --single-transaction`). Only when that worked does
it swap: the current database is renamed to `<db>_before_restore_<UTC stamp>` and the restored one to
`<db>`, so nothing created after the backup survives (including newer `schema_migrations` rows). If the
restore fails, the side database is dropped and the live database is left as it was. The old database is
**kept** (the script prints its name); once the restored data is verified, drop it with
`podman exec bee-with-me-db-1 dropdb -U rescuer <db>_before_restore_<stamp>` (Docker:
`docker exec …`). Until then the disk holds both copies.

Plain-text dumps (`beewithme_*.sql` from 1.7.1 or earlier) cannot be read by `pg_restore`: the script
says so and prints the `psql` commands that load one into a scratch database and turn it into a `.dump`
that it can restore. It refuses while something listens on
port 8000 (`-Force` / `--force` overrides), asks before replacing anything (`-Yes` / `--yes` skips the
question) and finally prints `python -m backend.db.migrate status`. It uses the same engine detection
as the backup (Podman, then Docker).

### 3. Backend

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r backend/requirements.txt
uvicorn backend.main:app
```

On a database that already holds data, pending migrations are only applied after a backup (see
"2. Database"); for hot reload on development data set `ALLOW_MIGRATE_WITHOUT_BACKUP=true`.

API: **http://localhost:8000**  
Interactive API docs: **http://localhost:8000/docs**

### 4. Frontend

```bash
cd frontend
npm install
npm run dev
```

App: **http://localhost:5173**

### 5. First login

A default admin account is created on first start if no users exist.

| Username | Password |
|----------|----------|
| `admin`  | `admin`  |

---

## Hardware

**Topology:** a USB gateway plugs into the server and receives radio transmissions from all field RescuerBee devices. There is no per-device USB connection — all frames arrive on a single port and are demultiplexed by `DevSN`.

- **USB HID** (active) — reads raw 64-byte HID packets from the gateway; configure `HID_VENDOR_ID` and `HID_PRODUCT_ID` in `.env`. This is the reader currently wired up in `main.py`.
- **Serial (LoRaWAN)** — `backend/hardware_reader/reader.py` has the frame-handling logic for a plain serial gateway, but its `run()` loop is currently commented out, so `SERIAL_PORT`/`SERIAL_BAUD` have no effect until it's re-enabled.

Check `GET /api/serial/status` (or the banner on the map view) to confirm the HID reader is actually connected — it reports `connected`, the VID:PID, and frames received.

**Before a device appears on the map**, an admin must register it in the Devices page with the matching serial number (`DevSN`). Until that row exists the reader discards the frame with a warning. Assigning the device to a volunteer links name, rank and team to the position.

### Windows

The USB gateway is a standard HID-class device, so **no vendor driver is needed** — Windows' inbox HID driver handles it automatically (unlike serial/FTDI gateways, which sometimes need a CDC driver installed). To confirm Windows sees it: Device Manager → look for it under **"Human Interface Devices"**. If it instead shows up under "Other devices" with a warning icon, Windows hasn't matched it to the HID class driver and `hid.device().open()` will fail — try a different USB port/cable before anything else.

Setup is otherwise the same as macOS/Linux:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r backend\requirements.txt
uvicorn backend.main:app
```

`pip install -r backend/requirements.txt` pulls prebuilt wheels for `hidapi` and `mgrs` on Windows (win_amd64), so no C compiler / Visual Studio Build Tools should be required for a supported Python version (3.10–3.13 as of writing).

Things that commonly trip up a fresh Windows box:

- **Device shows "connected" only in one app at a time.** HID devices can normally be opened by multiple processes, but if a vendor configuration tool (or a previous crashed run) is still holding it open, `dev.open()` raises `OSError`. Close other tools accessing the gateway and retry — the reader auto-reconnects every 5s.
- **Find the VID/PID** if you don't already have them: Device Manager → the device → Properties → Details tab → "Hardware Ids" shows `VID_xxxx&PID_xxxx`. Put those hex values into `HID_VENDOR_ID` / `HID_PRODUCT_ID` in `.env` (e.g. `0x0ACD`).
- **Uploads/tiles paths** (`backend/uploads`, `tiles/bgmountains`) are resolved relative to the `backend/` package location, not the current working directory, so starting the server from a shortcut or a different folder won't break photo uploads or offline map tiles.

### Serial protocol

**Full reference: [`docs/PROTOCOL.md`](docs/PROTOCOL.md)** — field tables, worked examples,
and a debugging checklist. Summary:

Every frame is wrapped as:

```
##<payload>@<CRC>\r\n
```

CRC is **CRC-16/CCITT-FALSE** (poly `0x1021`, init `0xFFFF`), computed over `##<payload>`
with the marker **included**, and transmitted as a **decimal** integer — not hex. Getting
either detail wrong means every frame fails CRC and is silently discarded.

#### Cmd=30 — RescuerBee location (25 fields)

```
##30,MsgId,DevSN,HWVer,SWVer,Hour,Min,Sec,Day,Mon,Year,GNSSStatus,Lat,Lng,Speed,Course,
    Satellites,Altitude,Flags,BattVol,CurrMothRxBeeRSSI,CurrMothRxBeeSNR,
    PrevBeeRxMothRSSI,PrevBeeRxMothSNR,EventID@<CRC>
```

| Field | Notes |
|---|---|
| GNSSStatus | `A` = valid fix, `V` = no fix. V frames are **recorded** (flagged `gnss_valid = FALSE`, anchored to the last known fix) — they prove the device is powered and in contact |
| Flags | Bit 0 (`0x01`) = repeater mode, Bit 1 (`0x02`) = SOS active |
| BattVol | Volts, e.g. `3.85` |
| RSSI / SNR ×4 | Link quality both directions — currently parsed past and discarded |
| EventID | Drives the duplicate filter (15 s window) |

#### Cmd=20 — RescuerRepeater heartbeat (11 fields)

```
##20,MsgId,DevSN,HWVer,SWVer,BattVol,CurrMRxDevRSSI,CurrMRxDevSNR,
    PrevDevRxMRSSI,PrevDevRxMSNR,EventID@<CRC>
```

Battery voltage only; stored in `repeater_events`, not shown on the map.

#### Cmd=1 — ACK (server → device)

```
##1,MsgId@<CRC>
```

Sent **after** a frame is handled successfully, so an unpersisted frame stays
unacknowledged and may be retransmitted.

---

## Importing volunteers

The Volunteers page has an **Import XLS** button. The file must be `.xls` or `.xlsx` and contain at minimum a name column. Supported column headers (Bulgarian or English, case-insensitive):

| Data | Recognised headers |
|---|---|
| Full name | `Доброволец`, `volunteer`, `name` |
| PIN | `ПИН`, `pin` |
| Phone | `Телефон`, `phone`, `tel`, `mobile` |

- Names are split on the first space: first word → first name, remainder → last name.
- Imported volunteers are assigned role `rescuer`.
- Re-importing the same file skips existing entries (matched by full name) and reports them as skipped in the response banner.
- PIN is stored as plaintext — it is an identification number, not a credential.

---

## Project structure

```
backend/
  main.py              FastAPI app, lifespan, static mounts
  auth.py              JWT issue/verify, bcrypt password hashing
  config.py            pydantic-settings; reads from .env
  database.py          asyncpg connection pool
  ws.py                WebSocket manager; pg_notify → broadcast
  hardware_reader/
    reader.py          DB handlers + serial loop (run() currently disabled)
    hid_reader.py      USB HID reader — the active path (50 Hz, frame reassembly, ACK)
    parser.py          Bee protocol frame parser; CRC-16/CCITT-FALSE (0x1021/0xFFFF)
  routers/
    auth.py            POST /api/auth/login, /refresh, GET /me
    users.py           CRUD + photo upload + XLS import
    groups.py          CRUD + member management
    devices.py         CRUD + reactivate + permanent delete
    locations.py       Live positions, SOS alerts, location history
    export.py          CSV / GeoJSON / PDF export
    hardware_reader.py GET /api/serial/status
    tiles.py           Tile download trigger + progress SSE
    ws.py              GET /ws WebSocket endpoint
    test.py            POST /api/test/simulate (dev only)
  db/
    migrate.py         Migration runner (python -m backend.db.migrate status|up)
    migrations/        Numbered SQL migrations; 0001_baseline.sql is the full base schema
  tests/               pytest suite (mocked DB, no real Postgres needed)
frontend/
  src/
    stores/            Pinia stores — auth.js, locations.js
    composables/       useMap.js (OpenLayers), useWebSocket.js, useSettings.js
    views/             Login, Map, Users, Groups, Devices, Export, About
    components/        AppLayout, SOSToast, SOSBanner
    router/            Vue Router — index.js
    i18n/              en.js, bg.js (vue-i18n v9)
    api/               Axios client (client.js) with JWT refresh interceptor
    nav-config.js      Navigation items with icons
docker/
  docker-compose.yaml  PostgreSQL 16 + PostGIS; tileserver-gl
lorawan/
  main.py              Standalone LoRaWAN bridge utility
tools/
  demo.py              Simulation script — injects fake frames via HTTP
  download_tiles.py    Tile download pipeline (z8–z18, Bulgaria bbox)
```

---

## Running tests

```bash
# Backend — run from the repo root. Use `python -m pytest` (not bare `pytest`) so the repo root
# is on sys.path and `import backend` resolves.
source .venv/bin/activate
python -m pytest backend/tests/                 # DB tests skip if PostgreSQL is unreachable
python -m pytest backend/tests/ --require-db    # …or fail instead, as CI does

# Frontend
cd frontend && npm test && npm run build
```

DB-backed tests create and drop throwaway `scratch_*` databases on the server from `.env`
(the `docker compose` database works); they never touch `rescuer_locator`'s data.

The `[sh]` script tests need a real bash. On Windows they use Git Bash (found next to `git.exe`, or
`%ProgramFiles%\Git\bin\bash.exe`), never the WSL launcher `C:\Windows\System32\bash.exe`; set
`BWM_TEST_BASH` to a bash path to override. Without one, the `[sh]` cases are skipped.

### Continuous integration

Every pull request and every push to `main` runs [`.github/workflows/ci.yml`](.github/workflows/ci.yml):

| Check | Runs on | What it verifies |
| --- | --- | --- |
| **Backend (Python 3.11)** | Ubuntu + `postgis/postgis:16-3.4` service | Byte-compiles `backend/`, full `pytest` suite with `--require-db` (migrations, PostGIS queries, fire alerts, PDF export, bash scripts) |
| **Scripts (Windows PowerShell)** | Windows | `start.ps1` / `backup.ps1` / `restore.ps1` behaviour tests, which only run on Windows |
| **Frontend (Node 22 / 24)** | Ubuntu | `npm ci`, Vitest suite, production `vite build`, `npm audit` of runtime deps (high+) |
| **Version & docs consistency** | Ubuntu | `backend/version.py` and `frontend/package.json` agree |
| **CI OK** | — | Aggregate gate: green only if all of the above passed. This is the required check on `main` |

Dependabot opens grouped weekly PRs for pip and npm, and monthly ones for GitHub Actions; they go through the same checks.

### Releases

Releases are cut by pushing a `vX.Y.Z` tag ([`.github/workflows/release.yml`](.github/workflows/release.yml)).
The workflow refuses to publish unless the tag matches `backend/version.py`, `frontend/package.json`
and a `## [X.Y.Z]` heading in `CHANGELOG.md`, then reruns the full CI suite on the tagged commit.
It publishes a GitHub Release whose notes come from that changelog section, with an offline install
bundle (`bee-with-me-vX.Y.Z.zip`) and its `.sha256`. Verify the checksum after copying the bundle to a field laptop:

```bash
shasum -a 256 -c bee-with-me-v1.7.2.zip.sha256                         # macOS / Linux
(Get-FileHash .\bee-with-me-v1.7.2.zip -Algorithm SHA256).Hash         # Windows: compare with the .sha256 file
```

---

## Contributing

`main` is protected: all changes land through a pull request. See [CONTRIBUTING.md](CONTRIBUTING.md) for the
workflow; in short:

1. Branch from `main` (`fix/…`, `feat/…`, or a release branch such as `1.7.2`).
2. Open a PR and fill in the template checklist.
3. **CI OK** must be green, and a code owner (see [`.github/CODEOWNERS`](.github/CODEOWNERS)) must approve.
   New commits pushed after an approval dismiss it, and all review threads must be resolved.
4. Squash-merge; the branch is deleted automatically.

---

## Real-time architecture

```
USB device → hardware_reader/reader.py → INSERT location_events → pg_notify('location_update')
                                                                          ↓
                                                     ws.py WSManager.listen_notifications()
                                                                          ↓
                                                     WebSocket broadcast → Pinia store → OL map
```

The WebSocket manager also broadcasts serial gateway connect/disconnect events so the map page shows a live status pill without polling.

---

## Changelog

See [CHANGELOG.md](CHANGELOG.md).
