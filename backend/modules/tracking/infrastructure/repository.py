"""SQL of the `tracking` module's HTTP side (statements copied unchanged from routers/locations.py)."""
from datetime import datetime
from uuid import UUID

import asyncpg


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
