# Changelog

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
