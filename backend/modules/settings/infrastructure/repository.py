"""SQL of the settings row. The statements, parameter order and connection methods are the ones the API tests read."""
import asyncpg

from ..domain.models import SettingsUpdate


async def fetch_settings(conn) -> asyncpg.Record | None:
    return await conn.fetchrow('SELECT * FROM settings WHERE id = 1')


async def row_exists(conn) -> bool:
    return await conn.fetchval('SELECT 1 FROM settings WHERE id = 1') is not None


async def update_settings(conn, body: SettingsUpdate, user_id) -> asyncpg.Record | None:
    """Full save with the optimistic-concurrency check on `updated_at`; None when the row is stale or missing."""
    return await conn.fetchrow(
        """UPDATE settings SET hq_latitude = $1, hq_longitude = $2, is_hq_alarm_enabled = $3,
               is_rescuer_alarm_enabled = $4, hq_radius_m = $5, rescuer_radius_m = $6,
               alarm_max_age_hours = $7, repeat_minutes = $8,
               is_rescuer_photo_on_map_enabled = $9, updated_by = $10
           WHERE id = 1 AND updated_at = $11 RETURNING *""",
        body.hq_latitude, body.hq_longitude, body.is_hq_alarm_enabled, body.is_rescuer_alarm_enabled,
        body.hq_radius_m, body.rescuer_radius_m, body.alarm_max_age_hours, body.repeat_minutes,
        body.is_rescuer_photo_on_map_enabled, user_id, body.expected_updated_at,
    )


async def update_hq(conn, latitude, longitude, user_id) -> asyncpg.Record | None:
    return await conn.fetchrow(
        """UPDATE settings SET hq_latitude = $1, hq_longitude = $2, updated_by = $3
           WHERE id = 1 RETURNING *""",
        latitude, longitude, user_id,
    )


async def set_initial_hq(conn, latitude, longitude, user_id) -> asyncpg.Record | None:
    return await conn.fetchrow(
        """UPDATE settings SET hq_latitude = $1, hq_longitude = $2, updated_by = $3
           WHERE id = 1 AND hq_latitude IS NULL AND updated_by IS NULL RETURNING *""",
        latitude, longitude, user_id,
    )
