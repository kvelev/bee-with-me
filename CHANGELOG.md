# Changelog

## [1.3.0] - 2026-04-19

### Offline map tiles — BG Mountains

- New background tile download pipeline: admin can trigger a full z8–z18 tile download for all of Bulgaria (bbox 22.3–28.7°E, 41.2–44.3°N) from the About page
- Tiles are stored at `tiles/bgmountains/` in the repo root and served by the backend via a FastAPI `StaticFiles` mount at `/tiles/bgmountains`
- Vite dev proxy forwards `/tiles/` to the backend so the map works without CORS issues in development

### Weather overlay

- Four weather tile overlays available in **Satellite mode only**: Clouds, Rain, Wind, Temperature
- Powered by OpenWeatherMap tile API v1.0; requires `VITE_OWM_API_KEY` in `.env`
- Buttons appear as a second row in the basemap controls when Satellite is active; clicking the active button toggles the overlay off
- Switching away from Satellite automatically removes the active weather overlay
- **Weather info panel**: when an overlay is active, a floating card shows current conditions for the map centre — temperature, feels-like, wind speed and direction, humidity, cloud cover, and city name with OWM weather icon; updates 700 ms after every map pan
- Panel uses `GET api.openweathermap.org/data/2.5/weather` with `units=metric`
- i18n: EN + BG for all new labels

### Database & backend

- Added `pin VARCHAR(20)` column to `users` table (stores rescuer ID number as plaintext)
- Added `is_radio_enthusiast BOOLEAN` and `radio_initials VARCHAR(20)` columns
- New indexes: `idx_sos_alerts_triggered`, `idx_user_groups_group_id`, `idx_devices_user_id`
- Daily background task deletes `location_events` older than `LOCATION_RETENTION_DAYS` (default 5, configurable via `.env`)
- `location_retention_days` setting added to `config.py`

### Pagination

- `GET /api/users/` and `GET /api/groups/` now return `{items, total, limit, offset}` instead of a flat array
- Default page size: 50 for users, 100 for groups; max 500
- Volunteers page shows a prev/next pagination bar; all other views request `limit=500` for full lists

## [1.2.1] - 2026-04-18

### Volunteer import (XLS)

- Added `python-calamine` (Rust-based Excel reader) as the primary parser for `.xls` files, replacing the previous multi-fallback chain that failed on OLE2 compound documents with non-standard FAT allocation
- Column matching now recognises Bulgarian headers: `ПИН` → pin, `Доброволец` → name, `Телефон` → phone
- Imported volunteers are now assigned role `rescuer` instead of `viewer`
- Re-importing the same file no longer creates duplicates — rows are skipped if a user with the same full name already exists, and the skip reason is included in the response

### PIN field

- PIN is returned by the API and pre-filled in the edit form when opening an existing volunteer
- PIN input is now a plain text field (previously masked as a password)

### Radio enthusiast

- Added `is_radio_enthusiast` boolean and `radio_initials VARCHAR(20)` fields to the users table and all related API endpoints
- Edit form shows a "Радиолюбител" checkbox; when checked, a call sign / initials field appears below it

## [1.2.0] - 2026-04-18

### Stale position indicator

- Map markers automatically grey out after 10 minutes of no new frame from the device
- Label text also fades so stale devices are visually distinct from live ones
- Staleness is re-evaluated every 60 seconds client-side, with no backend changes needed

### JWT refresh tokens

- Access tokens are now short-lived (15 minutes default via `ACCESS_TOKEN_EXPIRE_MINUTES`)
- Login response now includes a `refresh_token` (7-day lifetime, configurable via `REFRESH_TOKEN_EXPIRE_DAYS`)
- New `POST /api/auth/refresh` endpoint issues a fresh access + refresh token pair (token rotation)
- Axios interceptor automatically retries any 401 with a silent refresh before redirecting to login
- Concurrent requests that hit 401 simultaneously are queued and retried after a single refresh, not re-triggered N times

### Distance / bearing tool

- New **Measure** button in the basemap controls row
- When active the cursor becomes a crosshair; click once to set point A, again to set point B
- A dashed amber line draws between the two points and a readout appears at the top of the map showing distance in km and bearing in degrees
- Clicking a third time resets and starts a new measurement; toggling the button off clears everything

## [1.1.1] - 2026-04-18

### Bug fixes

- **SOS re-appears after page refresh** — `GET /api/locations/live` now joins against `sos_alerts WHERE resolved_at IS NULL` and overrides `sos_active` to `FALSE` for devices whose SOS was already resolved by an operator. Previously a resolved SOS would re-appear on every page refresh because the raw `sos_active` flag in `location_events` still reflected the device's transmitting state.

- **N+1 group fetch on map mount** — replaced the loop of individual `GET /api/groups/<id>` calls with a single `GET /api/groups/?include_members=true` endpoint that returns member lists inline via a `json_agg` join. Saves N round-trips on page load.

- **Serial gateway status now pushed via WebSocket** — eliminated the 5-second HTTP poll for `/api/serial/status`. The serial reader now calls `manager.broadcast()` directly when it connects or disconnects; the frontend WebSocket handler updates the store. A single HTTP fetch on page mount still seeds the initial state before the first WS event arrives.

## [1.1.0] - 2026-04-18

### Map — MGRS grid labels

- Graticule labels now switch format based on the active grid mode:
  - **MGRS grid on**: labels show MGRS coordinates (e.g. `34TFM`, `34TFM46`, `34TFM4136`)
  - **Lat/Lon grid on**: labels show decimal degrees (e.g. `25.0°E`, `42.0°N`)
- MGRS label precision scales with zoom level:
  - Zoom < 11 → 100 km grid square (`34TFM`)
  - Zoom 11–13 → 10 km precision (`34TFM46`)
  - Zoom ≥ 14 → 1 km precision (`34TFM4136`)
- Lat/Lon grid button now also toggles the graticule overlay (previously it only affected the cursor readout)
- Mouse cursor coordinate readout is unchanged

### Map — Rank filter

- Added a "Search by rank" input to the tracker panel sidebar
- Typing filters both the map markers and the tracker list to show only people whose rank matches (case-insensitive substring)
- Works in both Volunteers and Teams view modes
- A clear (✕) button appears when a filter is active
- i18n: EN (`Search by rank…`) and BG (`Търсене по звание…`)

### Serial / LoRaWAN gateway

- Fixed `SERIAL_PORT` / `SERIAL_BAUD` being read at module import time before `.env` was loaded — now reads from `settings` at runtime
- Added reconnect loop: reader retries every 5 s on serial or DB error instead of dying permanently
- Added `GET /api/serial/status` endpoint returning `{connected, port, baud, last_frame_at, frames_received, error}`
- Map page polls status every 5 s and shows a status pill (green = connected, red = disconnected) above the basemap controls, including port name and frame count

### SOS notifications

- Toast notification appears in the top-right corner when a device transitions into SOS state
- Notification shows the person's name, "SOS Activated" label, and timestamp
- Pulsing red glow border draws attention; auto-dismisses after 10 s or can be closed manually
- Three-beep audio alarm plays via Web Audio API on each new SOS event
- Multiple simultaneous SOS alerts stack vertically
- i18n: EN / BG

### Demo simulator (`tools/demo.py`)

- Elena (SOS_DEVICE) now transmits with `sos_active: true` every tick
- Terminal output marks her updates with `🚨 SOS`
- Simulate endpoint (`POST /api/test/simulate`) now accepts `sos_active` parameter, passes it to the DB insert and the pg_notify payload, and opens an `sos_alerts` row on first SOS so the pulsing badge in the tracker panel activates

### Bug fixes

- Fixed groups active/inactive toggle not working — `is_active` was missing from the `GET /api/groups/` response

### Internal

- Fixed graticule label cache not invalidating on mode switch (`renderedExtent_` reset before forced re-render)
- Bumped frontend (`package.json`) and backend (`main.py`) version to `1.1.0`

## [1.0.0] - initial release
