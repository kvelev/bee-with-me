from collections import defaultdict
from datetime import datetime
from typing import Annotated
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from ..auth import get_current_user
from ..database import get_conn

router = APIRouter(prefix='/api/locations', tags=['locations'])


@router.get('/live')
async def live_positions(
    conn: Annotated[asyncpg.Connection, Depends(get_conn)],
    _: Annotated[asyncpg.Record, Depends(get_current_user)],
):
    """Latest confirmed position for every active device."""
    rows = await conn.fetch("""
        SELECT DISTINCT ON (le.device_id)
            le.device_id, le.user_id,
            u.full_name, u.rank, u.photo_url, u.phone,
            d.dev_sn, d.name AS device_name,
            le.mgrs, le.latitude, le.longitude,
            le.altitude_m, le.speed_knots, le.battery_voltage,
            le.gnss_satellites, le.sos_active, le.repeater_mode,
            le.recorded_at,
            COALESCE(
                json_agg(json_build_object('id', g.id, 'name', g.name, 'color', g.color, 'is_leader', ug.is_leader))
                FILTER (WHERE g.id IS NOT NULL AND g.is_active = TRUE), '[]'
            ) AS groups
        FROM location_events le
        JOIN devices d ON d.id = le.device_id AND d.is_active = TRUE
        LEFT JOIN users u ON u.id = le.user_id
        LEFT JOIN user_groups ug ON ug.user_id = le.user_id
        LEFT JOIN groups g ON g.id = ug.group_id
        WHERE (le.user_id IS NULL OR u.is_active = TRUE)
        GROUP BY le.id, le.device_id, le.user_id, u.full_name, u.rank, u.photo_url, u.phone, d.dev_sn, d.name
        ORDER BY le.device_id, le.recorded_at DESC
    """)
    return [dict(r) for r in rows]


@router.get('/sos')
async def open_sos_alerts(
    conn: Annotated[asyncpg.Connection, Depends(get_conn)],
    _: Annotated[asyncpg.Record, Depends(get_current_user)],
):
    rows = await conn.fetch("""
        SELECT sa.id, sa.triggered_at,
               d.dev_sn, d.name AS device_name,
               u.full_name, u.rank
        FROM sos_alerts sa
        JOIN devices d ON d.id = sa.device_id
        LEFT JOIN users u ON u.id = sa.user_id
        WHERE sa.resolved_at IS NULL
        ORDER BY sa.triggered_at DESC
    """)
    return [dict(r) for r in rows]


@router.post('/sos/{alert_id}/resolve')
async def resolve_sos(
    alert_id: UUID,
    notes: str | None = None,
    conn: Annotated[asyncpg.Connection, Depends(get_conn)] = None,
    current_user: Annotated[asyncpg.Record, Depends(get_current_user)] = None,
):
    await conn.execute("""
        UPDATE sos_alerts
        SET resolved_at = NOW(), resolved_by = $2, notes = $3
        WHERE id = $1 AND resolved_at IS NULL
    """, alert_id, current_user['id'], notes)
    return {'resolved': True}


@router.get('/trail')
async def location_trail(
    conn: Annotated[asyncpg.Connection, Depends(get_conn)],
    _: Annotated[asyncpg.Record, Depends(get_current_user)],
    minutes: int = Query(30, ge=1, le=60),
):
    """Return all location events from the last N minutes, grouped by device_id."""
    rows = await conn.fetch("""
        SELECT le.device_id, le.latitude, le.longitude, le.recorded_at
        FROM location_events le
        JOIN devices d ON d.id = le.device_id AND d.is_active = TRUE
        WHERE le.recorded_at > NOW() - ($1 * INTERVAL '1 minute')
        ORDER BY le.device_id, le.recorded_at ASC
    """, minutes)
    grouped = defaultdict(list)
    for r in rows:
        grouped[str(r['device_id'])].append({
            'lat': r['latitude'],
            'lon': r['longitude'],
            'recorded_at': r['recorded_at'].isoformat(),
        })
    return dict(grouped)


@router.get('/{device_id}/history')
async def device_history(
    device_id: UUID,
    conn: Annotated[asyncpg.Connection, Depends(get_conn)],
    _: Annotated[asyncpg.Record, Depends(get_current_user)],
    from_dt: datetime | None = Query(None, alias='from'),
    to_dt: datetime | None = Query(None, alias='to'),
    limit: int = Query(500, le=5000),
    offset: int = 0,
):
    rows = await conn.fetch("""
        SELECT id, mgrs, latitude, longitude, altitude_m, speed_knots,
               gnss_satellites, battery_voltage, sos_active, recorded_at
        FROM location_events
        WHERE device_id = $1
          AND ($2::timestamptz IS NULL OR recorded_at >= $2)
          AND ($3::timestamptz IS NULL OR recorded_at <= $3)
        ORDER BY recorded_at DESC
        LIMIT $4 OFFSET $5
    """, device_id, from_dt, to_dt, limit, offset)
    return [dict(r) for r in rows]
