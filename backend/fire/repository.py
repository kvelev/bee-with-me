"""All SQL for the fire feature. Callers pass an asyncpg connection (and own the transaction)."""

from __future__ import annotations

import json
import logging
from datetime import datetime

import asyncpg

from .h3index import h3_r8
from .models import ALERT_OUT_SELECT, FireAlertOut
from .parse import BurntAreaRow, HotspotRow
from .proximity import AlarmSettings, Hotspot, NewAlert, OpenAlert, Target, Zone

logger = logging.getLogger(__name__)

_UPSERT_HOTSPOT = """
    INSERT INTO fire_hotspots (source, effis_id, acquired_at, latitude, longitude, h3_r8, effis_class)
    VALUES ($1::fire_data_source, $2, $3, $4, $5, $6, $7)
    ON CONFLICT (source, effis_id) DO UPDATE SET
        acquired_at  = EXCLUDED.acquired_at,
        latitude     = EXCLUDED.latitude,
        longitude    = EXCLUDED.longitude,
        h3_r8        = EXCLUDED.h3_r8,
        effis_class  = EXCLUDED.effis_class,
        last_seen_at = NOW()
"""
# Admin state (dismissed_*, notes, suppressed_by_zone_id) is deliberately absent from DO UPDATE.

_UPSERT_BURNT_AREA = """
    INSERT INTO fire_burnt_areas (source, effis_id, effis_fire_id, started_at, ended_at, area_ha, geometry)
    VALUES ($1::fire_data_source, $2, $3, $4, $5, $6, $7::jsonb)
    ON CONFLICT (source, effis_id) DO UPDATE SET
        effis_fire_id = EXCLUDED.effis_fire_id,
        started_at    = EXCLUDED.started_at,
        ended_at      = EXCLUDED.ended_at,
        area_ha       = EXCLUDED.area_ha,
        geometry      = EXCLUDED.geometry,
        last_seen_at  = NOW()
"""

_PRUNE_HOTSPOTS = """
    WITH d AS (
        DELETE FROM fire_hotspots h
        WHERE ((h.source <> 'field_report' AND h.last_seen_at < NOW() - INTERVAL '7 days')
            OR (h.source =  'field_report' AND h.acquired_at  < NOW() - INTERVAL '7 days'))
          AND NOT EXISTS (SELECT 1 FROM fire_alerts a WHERE a.hotspot_id = h.id)
        RETURNING 1)
    SELECT count(*) FROM d
"""

_PRUNE_BURNT_AREAS = """
    WITH d AS (DELETE FROM fire_burnt_areas WHERE last_seen_at < NOW() - INTERVAL '7 days' RETURNING 1)
    SELECT count(*) FROM d
"""

# Feed age is the age of the EFFIS data: field reports (source = 'field_report') are ours, not the feed's.
_LAST_SEEN_SQL = {
    'fire_hotspots': "SELECT max(last_seen_at) FROM fire_hotspots WHERE source <> 'field_report'",
    'fire_burnt_areas': 'SELECT max(last_seen_at) FROM fire_burnt_areas',
}


async def upsert_hotspots(conn: asyncpg.Connection, rows: list[HotspotRow]) -> None:
    if not rows:
        return
    await conn.executemany(_UPSERT_HOTSPOT, [
        (r.source, r.effis_id, r.acquired_at, r.latitude, r.longitude,
         h3_r8(r.latitude, r.longitude), r.effis_class)
        for r in rows
    ])


async def upsert_burnt_areas(conn: asyncpg.Connection, rows: list[BurntAreaRow]) -> None:
    if not rows:
        return
    await conn.executemany(_UPSERT_BURNT_AREA, [
        (r.source, r.effis_id, r.effis_fire_id, r.started_at, r.ended_at, r.area_ha, json.dumps(r.geometry))
        for r in rows
    ])


_PURGE_ZONES = """
    WITH d AS (DELETE FROM fire_suppression_zones WHERE disabled_at < NOW() - INTERVAL '48 hours' RETURNING 1)
    SELECT count(*) FROM d
"""


async def prune_fire_data(conn: asyncpg.Connection) -> dict[str, int]:
    return {
        'fire_hotspots': await conn.fetchval(_PRUNE_HOTSPOTS),
        'fire_burnt_areas': await conn.fetchval(_PRUNE_BURNT_AREAS),
        'fire_suppression_zones': await conn.fetchval(_PURGE_ZONES),
    }


async def anonymise_alerts(conn: asyncpg.Connection, retention_days: int) -> int:
    """DP-03: drop the named trace (user, device, ack/resolve actors, notes) from RESOLVED alerts once they are older
    than the location retention, so alerts never outlive the positions they were derived from. Open alerts are never
    touched; the rest of the row stays for after-action review. Keyed on the server clock (resolved_at).
    Returns the number of anonymised alerts."""
    return await conn.fetchval(
        "WITH u AS (UPDATE fire_alerts SET user_id = NULL, device_id = NULL, acknowledged_by = NULL,"
        " resolved_by = NULL, notes = NULL"
        " WHERE resolved_at IS NOT NULL AND resolved_at < NOW() - make_interval(days => $1::int)"
        " AND (user_id IS NOT NULL OR device_id IS NOT NULL OR acknowledged_by IS NOT NULL"
        "      OR resolved_by IS NOT NULL OR notes IS NOT NULL)"
        " RETURNING 1) SELECT COUNT(*) FROM u", retention_days)


async def anonymise_hotspots(conn: asyncpg.Connection, retention_days: int) -> int:
    """B51: personal fields of a hotspot whose alerts are all long resolved and whose own last activity is past the
    retention are cleared. Returns the number of anonymised hotspots (a count only, never a value)."""
    return await conn.fetchval(_ANONYMISE_HOTSPOTS, retention_days)


async def anonymise_resolved_alerts(conn: asyncpg.Connection, retention_days: int) -> int:
    """Both steps in order (alerts, then hotspots) for callers that want one call; returns the alert count. The
    start-up cleanup runs the steps separately so a failure in one is reported as that step (B55)."""
    alerts = await anonymise_alerts(conn, retention_days)
    await anonymise_hotspots(conn, retention_days)
    return alerts


# Last activity = newest of the feed sighting, the dismissal and the extinction (all server clock). A hotspot an open
# or recently resolved alert still points at keeps its fields: the operation record is still in use.
_ANONYMISE_HOTSPOTS = """
    WITH u AS (
        UPDATE fire_hotspots h
        SET dismissed_by = NULL, dismiss_notes = NULL, extinguished_by = NULL,
            reported_by = NULL, reported_device_id = NULL, notes = NULL
        WHERE GREATEST(h.last_seen_at, COALESCE(h.dismissed_at, '-infinity'::timestamptz),
                       COALESCE(h.extinguished_at, '-infinity'::timestamptz))
              < NOW() - make_interval(days => $1::int)
          AND NOT EXISTS (SELECT 1 FROM fire_alerts a
                          WHERE a.hotspot_id = h.id
                            AND (a.resolved_at IS NULL
                                 OR a.resolved_at >= NOW() - make_interval(days => $1::int)))
          AND (h.dismissed_by IS NOT NULL OR h.dismiss_notes IS NOT NULL OR h.extinguished_by IS NOT NULL
               OR h.reported_by IS NOT NULL OR h.reported_device_id IS NOT NULL OR h.notes IS NOT NULL)
        RETURNING 1)
    SELECT COUNT(*) FROM u
"""


async def list_hotspots(conn: asyncpg.Connection) -> list[asyncpg.Record]:
    return await conn.fetch(
        "SELECT * FROM fire_hotspots WHERE acquired_at > NOW() - INTERVAL '7 days' ORDER BY acquired_at DESC")


async def list_burnt_areas(conn: asyncpg.Connection) -> list[asyncpg.Record]:
    return await conn.fetch(
        "SELECT * FROM fire_burnt_areas WHERE last_seen_at > NOW() - INTERVAL '7 days' ORDER BY started_at DESC NULLS LAST")


async def last_seen_at(conn: asyncpg.Connection, table: str) -> datetime | None:
    sql = _LAST_SEEN_SQL.get(table)
    if sql is None:
        raise ValueError(f'unknown table {table!r}')
    return await conn.fetchval(sql)


class SettingsMissingError(RuntimeError):
    """The settings row (id = 1) is absent: the alarm cannot be evaluated honestly without it."""


async def load_alarm_settings(conn: asyncpg.Connection) -> tuple[AlarmSettings, Target | None]:
    row = await conn.fetchrow('SELECT * FROM settings WHERE id = 1')
    if row is None:
        raise SettingsMissingError('settings row (id=1) is missing')
    settings = AlarmSettings(row['is_hq_alarm_enabled'], row['is_rescuer_alarm_enabled'], row['hq_radius_m'],
                             row['rescuer_radius_m'], row['alarm_max_age_hours'], row['repeat_minutes'])
    hq = None
    if row['hq_latitude'] is not None:
        hq = Target('hq', None, None, row['hq_latitude'], row['hq_longitude'])
    return settings, hq


async def load_rescuer_targets(conn: asyncpg.Connection, max_age_min: int) -> list[Target]:
    # Latest row per active device, with or without a GNSS fix (a no-fix row carries the last known fix).
    # received_at is timestamptz, so asyncpg returns tz-aware UTC values (evaluate() precondition).
    rows = await conn.fetch("""
        SELECT d.id::text AS device_id, d.user_id::text AS user_id, le.latitude, le.longitude, le.received_at
        FROM devices d
        JOIN LATERAL (
            SELECT latitude, longitude, received_at FROM location_events
            WHERE device_id = d.id ORDER BY received_at DESC LIMIT 1
        ) le ON TRUE
        LEFT JOIN users u ON u.id = d.user_id
        WHERE d.is_active = TRUE
          AND le.received_at > NOW() - make_interval(mins => $1)
          AND (u.id IS NULL OR u.is_active = TRUE)
    """, max_age_min)
    return [Target('rescuer', r['device_id'], r['user_id'], r['latitude'], r['longitude'], r['received_at'])
            for r in rows]


async def load_evaluation_hotspots(conn: asyncpg.Connection, max_age_hours: int) -> list[Hotspot]:
    # Candidates in the age window plus anything an open alert still points at (so it can be resolved).
    rows = await conn.fetch("""
        SELECT id::text, source::text AS source, latitude, longitude, acquired_at,
               dismissed_at IS NOT NULL AS is_dismissed
        FROM fire_hotspots
        WHERE source <> 'field_report'
          AND (acquired_at > NOW() - make_interval(hours => $1)
               OR id IN (SELECT hotspot_id FROM fire_alerts WHERE resolved_at IS NULL))
    """, max_age_hours)
    return [Hotspot(r['id'], r['source'], r['latitude'], r['longitude'], r['acquired_at'], r['is_dismissed'])
            for r in rows]


async def load_active_zones(conn: asyncpg.Connection) -> list[Zone]:
    rows = await conn.fetch(
        'SELECT id::text, latitude, longitude, radius_m FROM fire_suppression_zones WHERE is_active = TRUE')
    return [Zone(r['id'], r['latitude'], r['longitude'], r['radius_m']) for r in rows]


async def load_open_alerts(conn: asyncpg.Connection) -> list[OpenAlert]:
    rows = await conn.fetch("""
        SELECT id::text, hotspot_id::text, target_type::text AS target_type, device_id::text
        FROM fire_alerts WHERE resolved_at IS NULL
    """)
    return [OpenAlert(r['id'], r['hotspot_id'], r['target_type'], r['device_id']) for r in rows]


async def set_suppression(conn: asyncpg.Connection, suppressed: dict[str, str | None]) -> None:
    if suppressed:
        await conn.executemany("""
            UPDATE fire_hotspots SET suppressed_by_zone_id = $2::uuid
            WHERE id = $1::uuid AND suppressed_by_zone_id IS DISTINCT FROM $2::uuid
        """, list(suppressed.items()))


async def insert_alert(conn: asyncpg.Connection, alert: NewAlert) -> str | None:
    return await conn.fetchval("""
        INSERT INTO fire_alerts (hotspot_id, target_type, device_id, user_id, distance_m)
        VALUES ($1::uuid, $2::fire_alert_target, $3::uuid, $4::uuid, $5)
        ON CONFLICT DO NOTHING
        RETURNING id::text
    """, alert.hotspot_id, alert.target_type, alert.device_id, alert.user_id, alert.distance_m)


async def resolve_alert(conn: asyncpg.Connection, alert_id: str, reason: str, resolved_by: str | None = None) -> bool:
    return bool(await conn.fetchval("""
        UPDATE fire_alerts
        SET resolved_at = NOW(), resolve_reason = $2::fire_alert_resolve_reason, resolved_by = $3::uuid
        WHERE id = $1::uuid AND resolved_at IS NULL
        RETURNING 1
    """, alert_id, reason, resolved_by))


async def resolve_disabled_alerts(conn: asyncpg.Connection, resolved_by=None, device_id=None, user_id=None) -> list[str]:
    """Resolve open RESCUER alerts whose device is inactive or whose current holder is inactive, as 'disabled'.

    The evaluation tick calls it unscoped with resolved_by None (covers every way of deactivating); the deactivate
    endpoints scope it to the device / user just deactivated and record the admin in resolved_by. A rescuer that is
    merely silent (stale or absent position) is not inactive and keeps its alert open (B40). Returns the resolved ids.
    """
    rows = await conn.fetch("""
        UPDATE fire_alerts a
        SET resolved_at = NOW(), resolve_reason = 'disabled', resolved_by = $1::uuid
        FROM devices d
        LEFT JOIN users u ON u.id = d.user_id
        WHERE d.id = a.device_id AND a.target_type = 'rescuer' AND a.resolved_at IS NULL
          AND (d.is_active = FALSE OR u.is_active = FALSE)
          AND ($2::uuid IS NULL OR d.id = $2::uuid)
          AND ($3::uuid IS NULL OR d.user_id = $3::uuid)
        RETURNING a.id::text AS id
    """, None if resolved_by is None else str(resolved_by),
        None if device_id is None else str(device_id), None if user_id is None else str(user_id))
    return [r['id'] for r in rows]


async def resolve_hq_alerts(conn: asyncpg.Connection, resolved_by) -> list[str]:
    """Resolve every open HQ alert as 'disabled', by the admin who cleared HQ.

    Clearing HQ is a decision, not missing data (B40 keeps an alert open only while data is missing): left
    open, an acknowledged alert would still own its hotspot (idx_fire_alerts_open_hq), so an HQ set again
    next to the same fire would never alarm. Returns the resolved ids.
    """
    rows = await conn.fetch("""
        UPDATE fire_alerts
        SET resolved_at = NOW(), resolve_reason = 'disabled', resolved_by = $1::uuid
        WHERE target_type = 'hq' AND resolved_at IS NULL
        RETURNING id::text AS id
    """, None if resolved_by is None else str(resolved_by))
    return [r['id'] for r in rows]


async def get_alert_out(conn: asyncpg.Connection, alert_id: str) -> FireAlertOut | None:
    row = await conn.fetchrow(ALERT_OUT_SELECT + ' WHERE a.id = $1::uuid', alert_id)
    return FireAlertOut.from_row(row) if row else None


async def mark_repeats_due(conn: asyncpg.Connection) -> list[str]:
    rows = await conn.fetch("""
        UPDATE fire_alerts a SET last_notified_at = NOW()
        FROM settings s
        WHERE s.id = 1 AND a.resolved_at IS NULL AND a.acknowledged_at IS NULL
          AND a.last_notified_at < NOW() - make_interval(mins => s.repeat_minutes)
        RETURNING a.id::text
    """)
    return [r['id'] for r in rows]


async def list_alerts(conn: asyncpg.Connection, state: str, limit: int, offset: int) -> list[FireAlertOut]:
    where = ' WHERE a.resolved_at IS NULL' if state == 'open' else ''
    # Open alerts: unacknowledged first, so beyond the page cap it is acknowledged ones that fall off, never an
    # unacknowledged one (BP-02). 'all' stays newest first.
    order = 'a.acknowledged_at IS NOT NULL, a.triggered_at DESC' if state == 'open' else 'a.triggered_at DESC'
    rows = await conn.fetch(ALERT_OUT_SELECT + where + f' ORDER BY {order} LIMIT $1 OFFSET $2', limit, offset)
    return [FireAlertOut.from_row(r) for r in rows]


async def count_alerts(conn: asyncpg.Connection, state: str) -> int:
    """Rows matching the `state` filter of list_alerts, ignoring limit/offset (X-Total-Count)."""
    where = ' WHERE resolved_at IS NULL' if state == 'open' else ''
    return int(await conn.fetchval('SELECT count(*) FROM fire_alerts' + where))


async def acknowledge_alert(conn: asyncpg.Connection, alert_id: str, user_id) -> tuple[FireAlertOut | None, bool]:
    """Idempotent. Acknowledging stops the repeats but never resolves the alert (BP-02)."""
    changed = await conn.fetchval("""
        UPDATE fire_alerts SET acknowledged_at = NOW(), acknowledged_by = $2::uuid
        WHERE id = $1::uuid AND resolved_at IS NULL AND acknowledged_at IS NULL
        RETURNING 1
    """, alert_id, str(user_id))
    return await get_alert_out(conn, alert_id), bool(changed)


async def acknowledge_all(conn: asyncpg.Connection, user_id, alert_ids=None) -> list[str]:
    """Acknowledge open alerts. With `alert_ids` only those (an alert the operator never saw stays unacknowledged);
    None keeps the old behaviour (every open alert)."""
    if alert_ids is None:
        rows = await conn.fetch("""
            UPDATE fire_alerts SET acknowledged_at = NOW(), acknowledged_by = $1::uuid
            WHERE resolved_at IS NULL AND acknowledged_at IS NULL
            RETURNING id::text
        """, str(user_id))
    else:
        rows = await conn.fetch("""
            UPDATE fire_alerts SET acknowledged_at = NOW(), acknowledged_by = $1::uuid
            WHERE resolved_at IS NULL AND acknowledged_at IS NULL AND id = ANY($2::uuid[])
            RETURNING id::text
        """, str(user_id), [str(i) for i in alert_ids])
    return [r['id'] for r in rows]


async def count_targets(conn: asyncpg.Connection) -> dict:
    from .proximity import TARGET_POSITION_MAX_AGE_MIN
    _, hq = await load_alarm_settings(conn)
    rescuers = await load_rescuer_targets(conn, TARGET_POSITION_MAX_AGE_MIN)
    return {'hq': hq is not None, 'rescuers': len(rescuers)}


# -- operator writes (T18) ----------------------------------------------------------------------------------------

async def dismiss_hotspot(conn: asyncpg.Connection, hotspot_id: str, user_id, notes: str | None):
    """Idempotent: the first dismisser and time stay; a re-dismiss without notes changes nothing. New notes replace the
    old ones and their author and time are recorded (B51): the person named is the one who wrote the text."""
    return await conn.fetchrow("""
        UPDATE fire_hotspots
        SET dismissed_at = CASE WHEN $3::text IS NOT NULL THEN NOW() ELSE COALESCE(dismissed_at, NOW()) END,
            dismissed_by = CASE WHEN $3::text IS NOT NULL THEN $2::uuid ELSE COALESCE(dismissed_by, $2::uuid) END,
            dismiss_notes = COALESCE($3::text, dismiss_notes)
        WHERE id = $1::uuid
        RETURNING *
    """, hotspot_id, str(user_id), notes)


async def latest_device_position(conn: asyncpg.Connection, device_id: str):
    # received_at is the server clock; recorded_at is the device's and may be wrong (BP-01)
    return await conn.fetchrow("""
        SELECT latitude, longitude, gnss_valid FROM location_events
        WHERE device_id = $1::uuid AND received_at > NOW() - INTERVAL '24 hours'
        ORDER BY received_at DESC LIMIT 1
    """, device_id)


async def insert_field_report(conn: asyncpg.Connection, latitude: float, longitude: float, user_id,
                              device_id: str | None, notes: str | None):
    return await conn.fetchrow("""
        INSERT INTO fire_hotspots (source, acquired_at, latitude, longitude, h3_r8,
                                   reported_by, reported_device_id, notes)
        VALUES ('field_report', NOW(), $1, $2, $3, $4::uuid, $5::uuid, $6)
        RETURNING *
    """, latitude, longitude, h3_r8(latitude, longitude), str(user_id), device_id, notes)


async def extinguish_field_report(conn: asyncpg.Connection, hotspot_id: str, user_id):
    return await conn.fetchrow("""
        UPDATE fire_hotspots
        SET extinguished_at = COALESCE(extinguished_at, NOW()),
            extinguished_by = COALESCE(extinguished_by, $2::uuid)
        WHERE id = $1::uuid AND source = 'field_report'
        RETURNING *
    """, hotspot_id, str(user_id))


async def list_zones(conn: asyncpg.Connection, include_disabled: bool) -> list[asyncpg.Record]:
    where = '' if include_disabled else ' WHERE is_active = TRUE'
    return await conn.fetch('SELECT * FROM fire_suppression_zones' + where + ' ORDER BY label')


async def create_zone(conn: asyncpg.Connection, data: dict, user_id):
    return await conn.fetchrow("""
        INSERT INTO fire_suppression_zones (label, latitude, longitude, radius_m, notes, created_by)
        VALUES ($1, $2, $3, $4, $5, $6::uuid)
        RETURNING *
    """, data['label'], data['latitude'], data['longitude'], data['radius_m'], data['notes'], str(user_id))


class ZoneStaleError(Exception):
    """The zone exists but changed since the client read it (expected_updated_at no longer matches)."""


async def _zone_write(conn: asyncpg.Connection, sql: str, zone_id: str, *args):
    """Run a version-guarded zone UPDATE (`id = $1 AND updated_at = $2` is the guard; $1 and $2 are fixed).
    None = no such zone; ZoneStaleError = the zone exists but its version moved (BP-02: no lost update)."""
    row = await conn.fetchrow(sql, zone_id, *args)
    if row is None:
        if await conn.fetchval('SELECT 1 FROM fire_suppression_zones WHERE id = $1::uuid', zone_id):
            raise ZoneStaleError(zone_id)
    return row


async def update_zone(conn: asyncpg.Connection, zone_id: str, data: dict, expected_updated_at: datetime, user_id):
    """Edit label/position/radius/notes. Activation is not touched here (set_zone_active), so an edit can never
    silently re-enable a zone someone disabled. `user_id` is kept for the call-site contract (audit is logged)."""
    return await _zone_write(conn, """
        UPDATE fire_suppression_zones
        SET label = $3, latitude = $4, longitude = $5, radius_m = $6, notes = $7
        WHERE id = $1::uuid AND updated_at = $2
        RETURNING *
    """, zone_id, expected_updated_at, data['label'], data['latitude'], data['longitude'], data['radius_m'],
        data['notes'])


async def set_zone_active(conn: asyncpg.Connection, zone_id: str, is_active: bool, expected_updated_at: datetime,
                          user_id):
    return await _zone_write(conn, """
        UPDATE fire_suppression_zones
        SET is_active = $3,
            disabled_at = CASE WHEN $3 THEN NULL ELSE COALESCE(disabled_at, NOW()) END,
            disabled_by = CASE WHEN $3 THEN NULL ELSE COALESCE(disabled_by, $4::uuid) END
        WHERE id = $1::uuid AND updated_at = $2
        RETURNING *
    """, zone_id, expected_updated_at, is_active, str(user_id))


async def disable_zone(conn: asyncpg.Connection, zone_id: str, user_id):
    return await conn.fetchrow("""
        UPDATE fire_suppression_zones
        SET is_active = FALSE, disabled_at = COALESCE(disabled_at, NOW()),
            disabled_by = COALESCE(disabled_by, $2::uuid)
        WHERE id = $1::uuid
        RETURNING *
    """, zone_id, str(user_id))
