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
from pydantic import BaseModel, Field, model_validator

import mgrs as mgrs_lib

from ..auth import require_role
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
    _=Depends(require_role('admin')),
):
    device = await conn.fetchrow(
        'SELECT id, user_id FROM devices WHERE id = $1 AND is_active = TRUE',
        body.device_id,
    )
    if device is None:
        raise HTTPException(status_code=404, detail='Device not found or inactive')

    lat = body.lat if body.lat is not None else round(random.uniform(LAT_MIN, LAT_MAX), 6)
    lon = body.lon if body.lon is not None else round(random.uniform(LON_MIN, LON_MAX), 6)
    return await record_position(conn, device, lat, lon, body.sos_active)


async def record_position(conn: asyncpg.Connection, device, lat: float, lon: float, sos_active: bool, *,
                          gnss_valid: bool = True, battery: float | None = None,
                          at: datetime | None = None) -> dict:
    """Insert one fabricated frame for `device` ({id, user_id}) and push it to the browsers.

    Shared by POST /simulate and the test-mode simulation (backend/simulation.py), which also uses:
    gnss_valid=False  a "no fix" frame, like the reader writes it: lat/lon must be the last fix;
    battery           a fixed voltage instead of a random one (low-battery scenario);
    at                a past contact time for recorded_at AND received_at (stale / lost scenarios)."""
    mgrs_str = _MGRS.toMGRS(lat, lon)
    now = at or datetime.now(timezone.utc)

    alt   = random.randint(0, 500)
    speed = round(random.uniform(0, 10), 1) if gnss_valid else 0.0
    sats  = random.randint(4, 12) if gnss_valid else 0
    bat   = battery if battery is not None else round(random.uniform(3.0, 4.2), 2)

    row = await conn.fetchrow(
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
        device['id'], device['user_id'], random.randint(0, 255), now,
        lat, lon, mgrs_str, alt, speed, sats, bat, sos_active, gnss_valid,
    )

    if sos_active:
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
        'gnss_valid':      gnss_valid,
        'sos_active':      sos_active,
        'repeater_mode':   False,
        'recorded_at':     now.isoformat(),
        'received_at':     now.isoformat(),
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
    _=Depends(require_role('admin')),
):
    """Quick helper to get device IDs for use in simulate."""
    rows = await conn.fetch("""
        SELECT d.id, d.dev_sn, d.name, u.full_name AS user_name
        FROM devices d LEFT JOIN users u ON u.id = d.user_id
        WHERE d.is_active = TRUE
    """)
    return [dict(r) for r in rows]


# ── Test mode (Settings page) ─────────────────────────────────────────────────
# Imported lazily: backend.simulation imports record_position from this module.

class SimulationStart(BaseModel):
    lat: float = Field(42.698, ge=-90, le=90)       # Sofia, like tools/demo.py
    lon: float = Field(23.322, ge=-180, le=180)
    interval: float = Field(3.0, ge=1, le=60)
    # Scenario (backend/simulation.Scenario): how many trackers are in each state
    trackers: int = Field(6, ge=1, le=12)
    sos: int = Field(1, ge=0, le=12)
    no_fix: int = Field(0, ge=0, le=12)
    stale: int = Field(0, ge=0, le=12)
    lost: int = Field(0, ge=0, le=12)
    low_battery: int = Field(0, ge=0, le=12)
    step_m: int = Field(300, ge=5, le=2000)
    spread_km: float = Field(5.0, ge=0.5, le=50)

    @model_validator(mode='after')
    def _states_fit(self):
        if self.sos + self.no_fix + self.stale + self.lost > self.trackers:
            raise ValueError('sos + no_fix + stale + lost cannot be more than trackers')
        if self.low_battery > self.trackers:
            raise ValueError('low_battery cannot be more than trackers')
        return self


@router.get('/simulation')
async def simulation_status(_=Depends(require_role('admin'))):
    from ..simulation import simulation
    return simulation.status()


@router.post('/simulation/start')
async def simulation_start(body: SimulationStart, _=Depends(require_role('admin'))):
    from ..simulation import Scenario, SimulationRunning, simulation
    scenario = Scenario(**body.model_dump(exclude={'lat', 'lon', 'interval'}))
    try:
        return await simulation.start(body.lat, body.lon, body.interval, scenario)
    except SimulationRunning:
        raise HTTPException(status_code=409, detail='Test mode is already running')


@router.post('/simulation/stop')
async def simulation_stop(_=Depends(require_role('admin'))):
    from ..simulation import simulation
    return await simulation.stop()


@router.post('/simulation/reset')
async def simulation_reset(conn: asyncpg.Connection = Depends(get_conn), _=Depends(require_role('admin'))):
    """Stop test mode and delete the demo trackers' positions and SOS alerts, so the next tester
    starts from an empty map. Demo accounts, devices and teams stay."""
    from ..simulation import reset, simulation
    status = await simulation.stop()
    return {**status, 'deleted': await reset(conn)}
