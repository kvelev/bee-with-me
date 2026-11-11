"""
Simulation endpoint — development only.
POST /api/test/simulate  →  injects a fake location event for a given device
and fires pg_notify so the WebSocket layer pushes it to the browser.
"""

import random
from datetime import datetime, timezone
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator

import mgrs as mgrs_lib

from ..auth import require_role
from ..database import get_conn
from ..modules.sos import api as sos_api
from ..modules.tracking import api as tracking_api

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

    row = await tracking_api.insert_simulated_position(
        conn, device_id=device['id'], user_id=device['user_id'], msg_id=random.randint(0, 255), at=now,
        latitude=lat, longitude=lon, mgrs=mgrs_str, altitude_m=alt, speed_knots=speed, gnss_satellites=sats,
        battery_voltage=bat, sos_active=sos_active, gnss_valid=gnss_valid,
    )

    if sos_active:
        await sos_api.open_simulated_alert(conn, device['id'], device['user_id'], now)

    active, personal = await tracking_api.person_for_live(conn, device['user_id'])
    if not active:
        raise HTTPException(status_code=400, detail='User is inactive')

    payload = tracking_api.location_update_payload(
        tracking_api.PositionFix(
            device_id=device['id'], user_id=device['user_id'], mgrs=mgrs_str,
            latitude=lat, longitude=lon, altitude_m=alt, speed_knots=speed, course_deg=None, battery_voltage=bat,
            gnss_satellites=sats, gnss_valid=gnss_valid, sos_active=sos_active, repeater_mode=False,
            recorded_at=now, received_at=now),
        personal,
    )
    # The simulation has never sent course_deg (the reader's message has it): the difference is kept.
    del payload['course_deg']
    await tracking_api.publish_position(conn, payload)

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

MIN_INTERVAL_S = 60    # seconds between simulated frames per tracker
MAX_INTERVAL_S = 600


class SimulationStart(BaseModel):
    lat: float = Field(42.698, ge=-90, le=90)       # Sofia, like tools/demo.py
    lon: float = Field(23.322, ge=-180, le=180)
    # Real trackers report about once a minute; faster simulated traffic would make the map, trails and
    # freshness behave unlike the field. 60 s is the floor for anything a tester can start.
    interval: float = Field(MIN_INTERVAL_S, ge=MIN_INTERVAL_S, le=MAX_INTERVAL_S)
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
