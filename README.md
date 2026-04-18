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
- **JWT authentication** — short-lived access tokens (15 min) with silent refresh via 7-day refresh tokens.

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
SERIAL_PORT=/dev/ttyUSB0          # USB path of the LoRaWAN gateway
SERIAL_BAUD=115200
ACCESS_TOKEN_EXPIRE_MINUTES=15
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

**Topology:** one USB LoRaWAN gateway plugs into the server and receives radio transmissions from all field RescuerBee devices. There is no per-device USB connection — all frames arrive on a single serial port and are demultiplexed by `DevSN`.

**Before a device appears on the map**, an admin must register it in the Devices page with the matching serial number (`DevSN`). Until that row exists the reader discards the frame with a warning. Assigning the device to a volunteer links name, rank and team to the position.

### Serial protocol

Every frame is wrapped as:

```
##<payload>@<CRC16-hex>\r\n
```

CRC polynomial: `0xACAC`, computed over the payload bytes.

#### Cmd=30 — RescuerBee location

```
##30,MsgId,DevSN,Hour,Min,Sec,Day,Mon,Year,GNSSStatus,Lat,Lng,Speed,Satellites,Altitude,Flags,BattVol@<CRC>
```

| Field | Notes |
|---|---|
| GNSSStatus | `A` = valid fix, `V` = no fix (frames with V are dropped) |
| Flags | Bit 0 = SOS active, Bit 1 = repeater mode |
| BattVol | Volts, e.g. `3.85` |

#### Cmd=20 — RescuerRepeater heartbeat

```
##20,MsgId,DevSN,BattVol@<CRC>
```

Battery voltage only; stored in `repeater_events`, not shown on map.

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
  config.py            Settings via pydantic-settings + .env
  database.py          asyncpg connection pool
  ws.py                WebSocket manager; pg_notify → broadcast
  hardware_reader/     Asyncio serial loop; frame parser (CRC 0xACAC)
  routers/
    auth.py            POST /api/auth/login, /refresh
    users.py           CRUD + photo upload + XLS import
    groups.py          CRUD + member management
    devices.py         CRUD
    locations.py       Live positions, location history
    export.py          CSV / GeoJSON / PDF export
    sos.py             SOS alert list + resolve
  db/
    schema.sql         Full PostgreSQL + PostGIS schema
frontend/
  src/
    stores/            Pinia stores (auth, locations)
    composables/       useMap.js (OpenLayers), useWebSocket.js
    views/             Page components (Map, Users, Groups, Devices, Export, About)
    components/        AppLayout, SosToast
    i18n/              en.js, bg.js (vue-i18n v9)
    api/               Axios client with JWT refresh interceptor
    nav-config.js      Navigation items with icons
docker/
  docker-compose.yml   PostgreSQL 16 + PostGIS
tools/
  demo.py              Simulation script — injects fake location frames
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
