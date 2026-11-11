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
