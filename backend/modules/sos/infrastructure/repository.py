"""SQL of the `sos` module's HTTP side (statements copied unchanged from routers/locations.py)."""
import json
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


# ── Writers used by the hardware reader (T542) ───────────────────────────────
# Statements copied unchanged from hardware_reader/reader.py; same connection, no transaction of their own.

async def has_open_alert(conn: asyncpg.Connection, device_id) -> bool:
    return await conn.fetchval(
        'SELECT EXISTS(SELECT 1 FROM sos_alerts WHERE device_id = $1 AND resolved_at IS NULL)',
        device_id,
    )


async def raise_sos(conn: asyncpg.Connection, *, device_id, user_id, dev_sn, triggered_at) -> bool:
    """Open an alert unless one is open already; True when this call opened one."""
    existing = await conn.fetchrow(
        'SELECT id FROM sos_alerts WHERE device_id = $1 AND resolved_at IS NULL',
        device_id,
    )
    if existing is not None:
        return False

    alert = await conn.fetchrow(
        """
        INSERT INTO sos_alerts (device_id, user_id, triggered_at)
        VALUES ($1, $2, $3) RETURNING id, triggered_at
        """,
        device_id, user_id, triggered_at,
    )

    who = await conn.fetchrow(
        'SELECT full_name, rank FROM users WHERE id = $1', user_id,
    )
    # The payload has to carry the alert id: the browser puts these straight into the SOS
    # banner, whose Resolve button posts back to /sos/{id}/resolve. Without it the button
    # posts "undefined" and the alert can never be cleared from the UI.
    await conn.execute(
        "SELECT pg_notify('sos_alert', $1)",
        json.dumps({
            'id':           str(alert['id']),
            'device_id':    str(device_id),
            'user_id':      str(user_id) if user_id else None,
            'dev_sn':       dev_sn,
            'full_name':    who['full_name'] if who else None,
            'rank':         who['rank'] if who else None,
            'triggered_at': alert['triggered_at'].isoformat(),
        }),
    )
    return True
