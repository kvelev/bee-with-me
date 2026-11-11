"""SQL of the `sos` module's HTTP side (statements copied unchanged from routers/locations.py)."""
from uuid import UUID

import asyncpg


async def fetch_open_alerts(conn: asyncpg.Connection) -> list[asyncpg.Record]:
    return await conn.fetch("""
        SELECT sa.id, sa.device_id, sa.triggered_at,
               d.dev_sn, d.name AS device_name,
               u.full_name, u.rank
        FROM sos_alerts sa
        JOIN devices d ON d.id = sa.device_id
        LEFT JOIN users u ON u.id = sa.user_id
        WHERE sa.resolved_at IS NULL
        ORDER BY sa.triggered_at DESC
    """)


async def resolve_alert(conn: asyncpg.Connection, alert_id: UUID, user_id: UUID, notes: str | None) -> None:
    await conn.execute("""
        UPDATE sos_alerts
        SET resolved_at = NOW(), resolved_by = $2, notes = $3
        WHERE id = $1 AND resolved_at IS NULL
    """, alert_id, user_id, notes)


# ── Writers used outside the hardware reader (T541) ──────────────────────────
# Each runs on the caller's connection and opens no transaction.

async def open_simulated_alert(conn: asyncpg.Connection, device_id, user_id, at) -> None:
    await conn.execute(
        """
        INSERT INTO sos_alerts (device_id, user_id, triggered_at)
        SELECT $1, $2, $3
        WHERE NOT EXISTS (
            SELECT 1 FROM sos_alerts
            WHERE device_id = $1 AND resolved_at IS NULL
        )
        """,
        device_id, user_id, at,
    )


async def forget_person(conn: asyncpg.Connection, user_id) -> None:
    await conn.execute('UPDATE sos_alerts SET user_id = NULL WHERE user_id = $1', user_id)
    await conn.execute('UPDATE sos_alerts SET resolved_by = NULL WHERE resolved_by = $1', user_id)


async def delete_device_alerts(conn: asyncpg.Connection, device_id) -> None:
    await conn.execute('DELETE FROM sos_alerts       WHERE device_id = $1', device_id)


async def delete_alerts_of_devices(conn: asyncpg.Connection, device_ids) -> int:
    return await conn.fetchval(
        'WITH d AS (DELETE FROM sos_alerts WHERE device_id = ANY($1::uuid[]) RETURNING 1) SELECT count(*) FROM d',
        device_ids)
