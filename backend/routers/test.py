"""
Simulation endpoint — development only.
POST /api/test/simulate  →  injects a fake location event for a given device
and fires pg_notify so the WebSocket layer pushes it to the browser.
"""

import json
import random
from datetime import datetime, timezone
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import mgrs as mgrs_lib

from ..auth import get_current_user
from ..database import get_conn

router = APIRouter(prefix='/api/test', tags=['test'])

_MGRS = mgrs_lib.MGRS()

# Bounding box around Bulgaria for random positions
LAT_MIN, LAT_MAX = 41.2, 44.2
LON_MIN, LON_MAX = 22.3, 28.6


class SimulateRequest(BaseModel):
    device_id: UUID
    lat: float | None = None   # random if omitted
    lon: float | None = None
    sos_active: bool = False


@router.post('/simulate')
async def simulate(
    body: SimulateRequest,
    conn: asyncpg.Connection = Depends(get_conn),
    _=Depends(get_current_user),
):
    device = await conn.fetchrow(
        'SELECT id, user_id FROM devices WHERE id = $1 AND is_active = TRUE',
        body.device_id,
    )
    if device is None:
        raise HTTPException(status_code=404, detail='Device not found or inactive')

    lat = body.lat if body.lat is not None else round(random.uniform(LAT_MIN, LAT_MAX), 6)
    lon = body.lon if body.lon is not None else round(random.uniform(LON_MIN, LON_MAX), 6)
    mgrs_str = _MGRS.toMGRS(lat, lon)
    now = datetime.now(timezone.utc)

    alt   = random.randint(0, 500)
    speed = round(random.uniform(0, 10), 1)
    sats  = random.randint(4, 12)
    bat   = round(random.uniform(3.0, 4.2), 2)

    row = await conn.fetchrow(
        """
        INSERT INTO location_events (
            device_id, user_id, msg_id, recorded_at,
            position, latitude, longitude, mgrs,
            altitude_m, speed_knots, gnss_satellites,
            battery_voltage, sos_active, repeater_mode, raw_flags
        ) VALUES (
            $1, $2, $3, $4,
            ST_SetSRID(ST_MakePoint($6, $5), 4326), $5, $6, $7,
            $8, $9, $10, $11, $12, FALSE, 0
        ) RETURNING id
        """,
        device['id'], device['user_id'], random.randint(0, 255), now,
        lat, lon, mgrs_str, alt, speed, sats, bat, body.sos_active,
    )

    if body.sos_active:
        await conn.execute(
            """
            INSERT INTO sos_alerts (device_id, user_id, triggered_at)
            SELECT $1, $2, $3
            WHERE NOT EXISTS (
                SELECT 1 FROM sos_alerts
                WHERE device_id = $1 AND resolved_at IS NULL
            )
            """,
            device['id'], device['user_id'], now,
        )

    user_row = await conn.fetchrow(
        'SELECT full_name, rank, photo_url, phone, is_active FROM users WHERE id = $1',
        device['user_id'],
    )
    if user_row and not user_row['is_active']:
        raise HTTPException(status_code=400, detail='User is inactive')

    group_rows = await conn.fetch("""
        SELECT g.id, g.name, g.color, ug.is_leader
        FROM user_groups ug
        JOIN groups g ON g.id = ug.group_id
        WHERE ug.user_id = $1 AND g.is_active = TRUE
    """, device['user_id'])
    groups = [
        {'id': str(r['id']), 'name': r['name'], 'color': r['color'], 'is_leader': r['is_leader']}
        for r in group_rows
    ]

    payload = json.dumps({
        'device_id':       str(device['id']),
        'user_id':         str(device['user_id']) if device['user_id'] else None,
        'full_name':       user_row['full_name'] if user_row else None,
        'rank':            user_row['rank'] if user_row else None,
        'photo_url':       user_row['photo_url'] if user_row else None,
        'phone':           user_row['phone'] if user_row else None,
        'mgrs':            mgrs_str,
        'latitude':        lat,
        'longitude':       lon,
        'altitude_m':      alt,
        'speed_knots':     speed,
        'battery_voltage': bat,
        'gnss_satellites': sats,
        'sos_active':      body.sos_active,
        'repeater_mode':   False,
        'recorded_at':     now.isoformat(),
        'groups':          groups,
    })
    await conn.execute("SELECT pg_notify('location_update', $1)", payload)

    return {
        'inserted': str(row['id']),
        'lat': lat,
        'lon': lon,
        'mgrs': mgrs_str,
    }


@router.get('/devices')
async def list_devices_for_test(
    conn: asyncpg.Connection = Depends(get_conn),
    _=Depends(get_current_user),
):
    """Quick helper to get device IDs for use in simulate."""
    rows = await conn.fetch("""
        SELECT d.id, d.dev_sn, d.name, u.full_name AS user_name
        FROM devices d LEFT JOIN users u ON u.id = d.user_id
        WHERE d.is_active = TRUE
    """)
    return [dict(r) for r in rows]
