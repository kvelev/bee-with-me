# Bee With Me

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
- Node.js 20+
- Docker + Docker Compose

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
cd docker && docker compose up -d && cd ..
```

The schema (PostGIS + all tables) is applied automatically on first start. To reset and re-apply the schema, destroying all data:

```bash
cd docker && docker compose down -v && docker compose up -d && cd ..
```

**After upgrading from an earlier version**, apply the migration for any new columns:

```sql
ALTER TABLE users ADD COLUMN IF NOT EXISTS pin VARCHAR(20);
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_radio_enthusiast BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS radio_initials VARCHAR(20);
```

### 3. Backend

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload
```

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
uvicorn backend.main:app --reload
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
    schema.sql         Full PostgreSQL + PostGIS schema
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
source .venv/bin/activate
pytest backend/tests/
```

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
