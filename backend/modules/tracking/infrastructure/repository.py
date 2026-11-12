"""SQL of the `tracking` module's HTTP side (statements copied unchanged from routers/locations.py)."""
import json
from datetime import datetime
from uuid import UUID

import asyncpg

from ..domain.payload import PersonalDetails


async def fetch_live(conn: asyncpg.Connection, max_age_hours) -> list[asyncpg.Record]:
    return await conn.fetch("""
        SELECT DISTINCT ON (le.device_id)
            le.device_id, le.user_id,
            u.full_name, u.rank, u.photo_url, u.phone,
            d.dev_sn, d.name AS device_name,
            le.mgrs, le.latitude, le.longitude,
            le.altitude_m, le.speed_knots, le.course_deg, le.battery_voltage,
            le.gnss_satellites, le.gnss_valid,
            (sa.id IS NOT NULL) AS sos_active,  -- open alert = SOS until resolved (B72)
            le.repeater_mode,
            le.recorded_at, le.received_at,
            COALESCE(
                json_agg(json_build_object('id', g.id, 'name', g.name, 'color', g.color, 'is_leader', ug.is_leader))
                FILTER (WHERE g.id IS NOT NULL AND g.is_active = TRUE), '[]'
            ) AS groups
        FROM location_events le
        JOIN devices d ON d.id = le.device_id AND d.is_active = TRUE
        LEFT JOIN users u ON u.id = le.user_id
        LEFT JOIN user_groups ug ON ug.user_id = le.user_id
        LEFT JOIN groups g ON g.id = ug.group_id
        LEFT JOIN sos_alerts sa ON sa.device_id = le.device_id AND sa.resolved_at IS NULL
        WHERE (le.user_id IS NULL OR u.is_active = TRUE)
          AND le.received_at > NOW() - ($1 * INTERVAL '1 hour')
        GROUP BY le.id, le.device_id, le.user_id, u.full_name, u.rank, u.photo_url, u.phone, d.dev_sn, d.name, sa.id
        ORDER BY le.device_id, le.received_at DESC
    """, max_age_hours)


async def fetch_trail(conn: asyncpg.Connection, minutes: int) -> list[asyncpg.Record]:
    return await conn.fetch("""
        SELECT le.device_id, le.latitude, le.longitude, le.recorded_at, le.received_at
        FROM location_events le
        JOIN devices d ON d.id = le.device_id AND d.is_active = TRUE
        WHERE le.gnss_valid = TRUE
          AND le.received_at > GREATEST(
            NOW() - ($1 * INTERVAL '1 minute'),
            COALESCE(d.assigned_at, '-infinity'::timestamptz)
        )
        ORDER BY le.device_id, le.received_at ASC
    """, minutes)


async def fetch_history(conn: asyncpg.Connection, device_id: UUID, from_dt: datetime | None,
                        to_dt: datetime | None, limit: int, offset: int) -> list[asyncpg.Record]:
    return await conn.fetch("""
        SELECT id, mgrs, latitude, longitude, altitude_m, speed_knots,
               gnss_satellites, battery_voltage, sos_active, recorded_at
        FROM location_events
        WHERE device_id = $1
          AND ($2::timestamptz IS NULL OR recorded_at >= $2)
          AND ($3::timestamptz IS NULL OR recorded_at <= $3)
        ORDER BY recorded_at DESC
        LIMIT $4 OFFSET $5
    """, device_id, from_dt, to_dt, limit, offset)


# ── Writers used outside the hardware reader (T541) ──────────────────────────
# Each runs on the caller's connection and opens no transaction.

async def insert_simulated_position(conn: asyncpg.Connection, *, device_id, user_id, msg_id, at, latitude,
                                    longitude, mgrs, altitude_m, speed_knots, gnss_satellites, battery_voltage,
                                    sos_active, gnss_valid) -> asyncpg.Record:
    return await conn.fetchrow(
        """
        INSERT INTO location_events (
            device_id, user_id, msg_id, recorded_at,
            position, latitude, longitude, mgrs,
            altitude_m, speed_knots, gnss_satellites,
            battery_voltage, sos_active, repeater_mode, raw_flags, gnss_valid, received_at
        ) VALUES (
            $1, $2, $3, $4,
            ST_SetSRID(ST_MakePoint($6, $5), 4326), $5, $6, $7,
            $8, $9, $10, $11, $12, FALSE, 0, $13, $4
        ) RETURNING id
        """,
        device_id, user_id, msg_id, at,
        latitude, longitude, mgrs, altitude_m, speed_knots, gnss_satellites, battery_voltage, sos_active,
        gnss_valid,
    )


async def person_of(conn: asyncpg.Connection, user_id) -> asyncpg.Record | None:
    return await conn.fetchrow(
        'SELECT full_name, rank, photo_url, phone, is_active FROM users WHERE id = $1',
        user_id,
    )


async def is_person_active(conn: asyncpg.Connection, user_id) -> bool | None:
    """The thin mode's only read of `users` on the live path; None when there is no such person."""
    row = await conn.fetchrow('SELECT is_active FROM users WHERE id = $1', user_id)
    return None if row is None else row['is_active']


async def groups_of(conn: asyncpg.Connection, user_id) -> list[dict]:
    rows = await conn.fetch("""
        SELECT g.id, g.name, g.color, ug.is_leader
        FROM user_groups ug
        JOIN groups g ON g.id = ug.group_id
        WHERE ug.user_id = $1 AND g.is_active = TRUE
    """, user_id)
    return [
        {'id': str(r['id']), 'name': r['name'], 'color': r['color'], 'is_leader': r['is_leader']}
        for r in rows
    ]


async def person_for_live(conn: asyncpg.Connection, user_id, with_details: bool):
    """(active, PersonalDetails | None) for the live message; `active` is False for an inactive person.

    with_details=True runs today's two reads (`person_of`, then `groups_of` only for an active person); False runs
    one `is_person_active` and builds no personal part."""
    if not with_details:
        return await is_person_active(conn, user_id) is not False, None
    row = await person_of(conn, user_id)
    if row and not row['is_active']:
        return False, None
    groups = await groups_of(conn, user_id)
    return True, PersonalDetails(
        full_name=row['full_name'] if row else None, rank=row['rank'] if row else None,
        phone=row['phone'] if row else None, photo_url=row['photo_url'] if row else None, groups=groups)


async def publish_position(conn: asyncpg.Connection, payload: dict) -> None:
    await conn.execute("SELECT pg_notify('location_update', $1)", json.dumps(payload))


async def forget_person(conn: asyncpg.Connection, user_id) -> None:
    await conn.execute('UPDATE location_events SET user_id = NULL WHERE user_id = $1', user_id)


async def delete_device_positions(conn: asyncpg.Connection, device_id) -> None:
    await conn.execute('DELETE FROM location_events  WHERE device_id = $1', device_id)


async def delete_device_heartbeats(conn: asyncpg.Connection, device_id) -> None:
    await conn.execute('DELETE FROM repeater_events  WHERE device_id = $1', device_id)


async def delete_positions_of_devices(conn: asyncpg.Connection, device_ids) -> int:
    return await conn.fetchval(
        'WITH d AS (DELETE FROM location_events WHERE device_id = ANY($1::uuid[]) RETURNING 1) SELECT count(*) FROM d',
        device_ids)


# ── Writers used by the hardware reader (T542) ───────────────────────────────
# Statements copied unchanged from hardware_reader/reader.py; same connection, no transaction of their own.

async def last_fix(conn: asyncpg.Connection, device_id) -> asyncpg.Record | None:
    return await conn.fetchrow(
        """
            SELECT latitude, longitude, mgrs FROM location_events
            WHERE device_id = $1 AND gnss_valid = TRUE
            ORDER BY received_at DESC LIMIT 1
            """,
        device_id,
    )


async def previous_sos_flag(conn: asyncpg.Connection, device_id) -> bool | None:
    return await conn.fetchval(
        'SELECT sos_active FROM location_events WHERE device_id = $1 ORDER BY received_at DESC LIMIT 1',
        device_id,
    )


async def insert_position(conn: asyncpg.Connection, *, device_id, user_id, msg_id, recorded_at, received_at,
                          latitude, longitude, mgrs, altitude_m, speed_knots, course_deg, gnss_satellites,
                          battery_voltage, sos_active, repeater_mode, raw_flags, gnss_valid) -> None:
    await conn.execute(
        """
        INSERT INTO location_events (
            device_id, user_id, msg_id, recorded_at, received_at,
            position, latitude, longitude, mgrs,
            altitude_m, speed_knots, course_deg, gnss_satellites,
            battery_voltage, sos_active, repeater_mode, raw_flags, gnss_valid
        ) VALUES (
            $1, $2, $3, $4, $5,
            ST_SetSRID(ST_MakePoint($7, $6), 4326), $6, $7, $8,
            $9, $10, $11, $12,
            $13, $14, $15, $16, $17
        )
        """,
        device_id, user_id, msg_id, recorded_at, received_at,
        latitude, longitude, mgrs,
        altitude_m, speed_knots, course_deg, gnss_satellites,
        battery_voltage, sos_active, repeater_mode, raw_flags,
        gnss_valid,
    )


async def insert_heartbeat(conn: asyncpg.Connection, device_id, msg_id, battery_voltage) -> None:
    await conn.execute(
        'INSERT INTO repeater_events (device_id, msg_id, battery_voltage) VALUES ($1, $2, $3)',
        device_id, msg_id, battery_voltage,
    )


async def delete_positions_older_than(conn: asyncpg.Connection, days: int) -> int:
    """Retention (DP-03): delete the positions older than `days`; returns how many went."""
    deleted = await conn.fetchval(
        "WITH d AS (DELETE FROM location_events"
        " WHERE recorded_at < NOW() - ($1 || ' days')::interval RETURNING 1)"
        " SELECT COUNT(*) FROM d",
        str(days),
    )
    return deleted or 0
