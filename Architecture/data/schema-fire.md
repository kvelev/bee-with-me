# Schema: fire data and alarms

**Version:** 0.2 (Phase C)
**Status:** Draft
**Last updated:** 2026-11-07
**Source of truth:** `backend/db/migrations/0002_fire_data.sql` (fire data), `0003_settings.sql` (settings),
`0004_fire_alerts.sql` (alerts, suppression zones) and `0005_rescuer_photo_on_map.sql` (one settings column).
All are written and applied; the migration SQL wins over this summary.

Fire tables store coordinates as `latitude`/`longitude` columns and polygons as GeoJSON in `JSONB`, with no
PostGIS dependency, and use time-ordered `uuid_generate_v7()` keys (defined in `0002`).

---

## fire_hotspots

Active-fire detections from EFFIS (`viirs`, `modis`) and field reports (`field_report`).

| Column | Notes |
|--------|-------|
| `id` | UUID v7 |
| `source` | `fire_data_source` enum |
| `effis_id` | Null exactly when `source = 'field_report'` (`CHECK`); `UNIQUE (source, effis_id)` |
| `acquired_at` | Satellite acquisition or report time |
| `latitude`, `longitude` | `CHECK` ranges |
| `h3_r8` | H3 cell, resolution 8 (see `docs/research/2026-10-02-h3-proximity.md`) |
| `effis_class` | |
| `first_seen_at`, `last_seen_at` | Set by the poller; `last_seen_at` drives pruning |
| `dismissed_at`, `dismissed_by`, `dismiss_notes` | Admin dismisses a false detection |
| `reported_by`, `reported_device_id` | Field reports |
| `extinguished_at`, `extinguished_by` | Field reports marked out |
| `notes`, `created_at` | |
| `suppressed_by_zone_id` | Added by `0004`: FK to `fire_suppression_zones`, `ON DELETE SET NULL` |

Indexes: `acquired_at` DESC, `last_seen_at`. Admin columns are never overwritten by a feed refresh.

Lifetime: the backend's daily cleanup deletes feed hotspots 7 days after `last_seen_at` and field reports 7 days
after `acquired_at`, except a hotspot that any `fire_alerts` row still points at. Separately, the personal fields
(`dismissed_by`, `dismiss_notes`, `extinguished_by`, `reported_by`, `reported_device_id`, `notes`) are cleared once
the hotspot's last activity is older than `location_retention_days` (DP-03).

## fire_burnt_areas

`id` (v7), `source` (not `field_report`), `effis_id` (UNIQUE with `source`), `effis_fire_id`, `started_at`,
`ended_at`, `area_ha`, `geometry` (GeoJSON, JSONB), `first_seen_at`, `last_seen_at`, `created_at`.
Index on `last_seen_at`. Deleted by the daily cleanup 7 days after `last_seen_at`.

## settings (`0003`, `0005`)

Single row (`id = 1`, `CHECK`), seeded by the migration and written by admins through `/api/settings`; replaces HQ
in browser localStorage. `updated_at` is maintained by a trigger.

| Column | Notes |
|--------|-------|
| `hq_latitude`, `hq_longitude` | Both set or both null (`CHECK`) |
| `is_hq_alarm_enabled`, `is_rescuer_alarm_enabled` | Fire alarm switches, default on |
| `hq_radius_m`, `rescuer_radius_m` | Defaults 10 000 m and 3 000 m; 100 to 100 000 |
| `alarm_max_age_hours` | Default 24; 1 to 168. Older hotspots raise no alarm |
| `repeat_minutes` | Default 5; 1 to 60. Repeat interval of an unacknowledged alarm |
| `is_rescuer_photo_on_map_enabled` | Default on; shows the volunteer photo on the map marker (`0005`) |
| `updated_by`, `updated_at` | Audit |

## fire_alerts (`0004`)

One open alert per (target, hotspot): `hotspot_id` (FK `RESTRICT`), `target_type` (`hq` | `rescuer`), `device_id`
(only for `rescuer`, `CHECK`), `user_id`, `distance_m`, `triggered_at`, `last_notified_at` (repeat timer),
`acknowledged_at`/`by`, `resolved_at`/`by`, `resolve_reason` (`aged_out`, `out_of_range`, `dismissed`,
`suppressed`, `disabled`; set exactly when `resolved_at` is set, `CHECK`), `notes`. Partial unique indexes keep one
open alert per hotspot for HQ and per hotspot and device for a rescuer. Written only by the fire alarm service;
acknowledged by users. Rows are never deleted by cleanup: once resolved and older than `location_retention_days`,
the named trace (`user_id`, `device_id`, `acknowledged_by`, `resolved_by`, `notes`) is cleared and the rest stays
for after-action review. Open alerts are never touched.

## fire_suppression_zones (`0004`)

`id`, `label`, `latitude`, `longitude`, `radius_m` (50 to 20 000, default 1 000), `is_active` (always equal to
`disabled_at IS NULL`, `CHECK`), `disabled_at`/`by`, `notes`, `created_by`, `created_at`, `updated_at`. Admin
managed. Hotspots inside an active zone do not raise alarms. A disabled zone is deleted after 48 hours.

> ⚠️ **Requires stakeholder input (owner):** the 7-day fire data window, the 48-hour zone window and the
> reuse of `location_retention_days` for anonymising alerts and hotspots are implemented defaults, not owner
> decisions. Confirm them, and whether fire alerts are part of the operation record under BR-09.

---

## Corrections on restore (2026-11-07)

Restored from `b73eeed`; the earlier text predated the code. Changed: `settings`, `fire_alerts` and
`fire_suppression_zones` are no longer *target* (migrations `0003`, `0004` are written); added the settings
columns and `0005`, the missing alert and zone columns and checks, and the lifetime rules from
`backend/fire/repository.py`. Fire tables are not touched by `0006` (per-type device serials) or `0007`
(repeater location), which are described in [schema-core.md](schema-core.md).
