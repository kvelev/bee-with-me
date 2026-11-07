# Data classification register: Bee With Me

**Version:** 0.2 (Phase C)
**Status:** Draft (classification levels proposed, to be confirmed by the owner)
**Last updated:** 2026-11-07

Mutable supporting document. Every store of data in the system appears here with its classification, who
may read it and how long it lives (DP-03). Add a row in the same pull request that adds a new store, field or
copy of data.

---

## 1. Classification levels

| Level | Meaning | Handling |
|-------|---------|----------|
| **Restricted** | Personal data whose leak can harm a person: health data, contact data, photos, positions of people | Only on the field machine; only logged-in users who need it; never in logs; exports are deliberate operator actions |
| **Confidential** | Personal data with lower harm, and operational records: names, ranks, team membership, alarms | Only on the field machine; logged-in users |
| **Internal** | Data about equipment and configuration | Field machine; contributors may see examples |
| **Public** | Data that comes from public sources | No restriction on reading; attribution may apply |

> ⚠️ **Requires stakeholder input (owner):** confirm these levels, and whether partner organisations (the
> military in particular) require a stricter handling of their personnel's data.

**Lawful basis** ([ADR 16](../decisions/0016-lawful-basis-asp-contract.md)): the volunteer's contract with ASP
covers ordinary personal data. Special-category data (blood type, possibly health notes) is not covered; it is
marked **Special** in the register below until the owner confirms a basis (R-19). The system does not record
descriptions of a person's medical condition (owner, 2026-10-04); free-text notes must not be used for that.

> 📝 **Assumption:** blood type is health data (GDPR Article 9); a person's live position counts as
> Restricted because it reveals where they are.

---

## 2. Register

### 2.1 Database

| Store | Data | Level | Who can read today | Lifetime today | Target lifetime |
|-------|------|-------|--------------------|----------------|-----------------|
| `users`: blood type | Health data, **Special** (Article 9) | Restricted | Any logged-in user | Until the person is deleted | ⚠️ basis not confirmed (R-19, ADR 16) |
| `users`: phone, email, photo path, notes | Personal | Restricted | Any logged-in user (`GET /api/users`) | Until the person is deleted | ⚠️ BR-09 |
| `users`: `pin` | Volunteer's identification PIN (an identifier, not a secret) | Confidential | Any logged-in user (admins only, in practice) | Until the person is deleted | ⚠️ BR-09 |
| `users`: password hash | Credential | Restricted | Backend only | Until changed | Unchanged |
| `users`: name, rank, radio initials, role | Personal | Confidential | Any logged-in user | Until the person is deleted | ⚠️ BR-09 |
| `groups`, `user_groups` | Teams, organisations | Confidential | Any logged-in user | Until deleted | Unchanged |
| `devices` | Equipment, assignment; a repeater's hand-set `site_latitude`/`site_longitude` (migration 0007) is the position of equipment, not of a person | Internal | Any logged-in user | Until deleted; deleting a device also deletes its `sos_alerts`, `location_events` and `repeater_events` | Unchanged |
| `location_events` | Positions of people | Restricted | Any logged-in user; every `/ws` client | 90 days (`location_retention_days`, keyed on `recorded_at`) | ⚠️ BR-09 vs R-20; keyed on `received_at` |
| `repeater_events` | Equipment telemetry | Internal | Not exposed by the API | No cleanup | ⚠️ define (DP-03) |
| `sos_alerts` | Alarms with person | Confidential | Any logged-in user; every `/ws` client | No cleanup | ⚠️ BR-09 |
| `fire_hotspots` (EFFIS), `fire_burnt_areas` | Public fire data | Public | Any logged-in user | Deleted by the daily cleanup 7 days after `last_seen_at` (a hotspot with an alert is kept) | ⚠️ owner to confirm 7 days |
| `fire_hotspots` (field reports) | Observation with reporter | Confidential | Any logged-in user | Deleted 7 days after `acquired_at` (unless an alert points at it); reporter, dismisser and notes cleared after `location_retention_days` | ⚠️ BR-09 |
| `fire_alerts` | Alarm with person and distance | Confidential | Any logged-in user; every `/ws` client | Row kept; once resolved and older than `location_retention_days`, user, device, actors and notes are cleared (open alerts untouched) | ⚠️ BR-09: whether the anonymised row may stay |
| `fire_suppression_zones` | Circle where fire alarms are silenced | Internal | Any logged-in user | Disabled zones deleted after 48 hours | Unchanged |
| `settings` | HQ location, alarm radii and switches, photo-on-map switch | Confidential | Any logged-in user | Single row | Unchanged |

### 2.2 Files and channels

| Store or channel | Data | Level | Who can read today | Lifetime today |
|------------------|------|-------|--------------------|----------------|
| `backend/uploads/` | Volunteer photos | Restricted | **Anyone on the laptop** (`/uploads` is not authenticated, R-09; loopback only, ADR 12) | Until deleted; orphaned files stay (`todo.md`) |
| `/ws` `location_update` | Name, rank, **phone, photo path**, position | Restricted | Anyone on the laptop: open by design (ADR 15), loopback only (ADR 12) | Transient |
| `/ws` `sos_alert` | Name, rank, device | Confidential | Anyone on the laptop: open by design (ADR 15) | Transient |
| `/ws` `fire_alert`, `fire_alert_repeat`, `fire_alert_updated` | Name, rank, device, distance, hotspot position; never phone, photo path or HQ position; HQ distance rounded to 100 m | Confidential | Anyone on the laptop: open by design (ADR 15), loopback only (ADR 12) | Transient |
| Backups (`data/backups/*.dump`) | Whole database | Restricted | Users of the field machine with file access | Pruned by count |
| Restore copy (`<db>_before_restore_<time>`) | Whole database | Restricted | Database users | Until the operator drops it (R-14) |
| Exports (CSV, GeoJSON, PDF) | Positions with names | Restricted | Whoever gets the file | Outside the system's control |
| Application logs | IDs, counts, frame dumps | Internal (DP-02: no names, phones, positions) | Users of the field machine | ⚠️ define |
| Offline tiles (`tiles/`, `tile-server/maps/*.mbtiles`) | Map tiles | Public | Anyone; the Node tile server sends `Access-Control-Allow-Origin: *` | Until deleted |

> ⚠️ **Requires stakeholder input (owner):** where backups are stored physically (same disk, USB drive,
> another machine) and whether they are encrypted.

> ⚠️ **Requires technical clarification:** the HID reader logs raw packets at INFO level; check that a raw
> frame (which contains a position) does not break DP-02 in logs.

---

## 3. Data sovereignty

All data stays on the field machine (DP-01, [ADR 2](../decisions/0002-single-field-machine-intranet-deployment.md)).
Outbound requests carry no personal data: the fire poller sends only a bounding box to EFFIS. The browser
sends the map area to online tile providers and OpenWeatherMap when those layers are used (R-04, R-05).

---

## Corrections on restore (2026-11-07)

Restored from `b73eeed`. Changed: `fire_alerts` and `settings` are no longer *target* (migrations `0003`, `0004`
exist); fire data and alert lifetimes now state what `backend/main.py` and `backend/fire/repository.py` do (7-day
prune, anonymisation after `location_retention_days`); added `fire_suppression_zones`, the repeater site position
(`0007`), the cascade on device delete, and the second offline tile location. Added the `/ws` fire alert messages (`ws.py`, `fire/models.py`). Unchanged on purpose: RSSI and SNR are parsed
(`parser.py`) but not stored, so they add no row; revisit if a migration starts storing them.
