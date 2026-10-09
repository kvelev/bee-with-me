"""
Test mode — the in-server version of tools/demo.py, started and stopped from the Settings page.

Seeds the same demo volunteers, trackers and groups as tools/demo.py (idempotently: existing rows
are reused and reactivated), plus up to six extra trackers without photo or team, then sends frames
every `interval` seconds through routers/test.record_position, so the map, trails, SOS and freshness
behave exactly as with real frames. A Scenario picks how many trackers are in each state:

    sos          moving, SOS active                 no_fix   in contact, no GPS fix (stays at its last fix)
    stale        one report 15 min ago, then silent lost     one report 45 min ago, then silent
    low_battery  battery 3.2–3.4 V (overlaps the others)    all others move normally

Reset deletes the demo trackers' positions and SOS alerts (accounts and devices stay).

Only reachable when ENABLE_TEST_ENDPOINTS=true (the routes live in routers/test.py). State is
in-process: a backend restart stops the simulation. Unlike the CLI script, the demo volunteers
get an unusable random password — they are map markers, not accounts.
"""

from __future__ import annotations

import asyncio
import logging
import random
import secrets
import shutil
import uuid
from contextlib import suppress
from dataclasses import dataclass, field
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import asyncpg

from .auth import hash_password
from .database import get_pool
from .routers.test import record_position

logger = logging.getLogger(__name__)

PERSONAS_DIR = Path(__file__).resolve().parent.parent / 'tools' / 'demo-user-personas'
UPLOADS_DIR = Path(__file__).resolve().parent / 'uploads'

# Kept in step with tools/demo.py (DEMO_USERS / DEMO_GROUPS / SOS_DEVICE)
DEMO_USERS = [
    {'first_name': 'Ivan',   'last_name': 'Petrov',    'phone': '+359888000001', 'pin': '1234',
     'username': 'demo_ivan',     'rank': 'Sergeant',   'blood_type': 'A+',
     'photo': 'ivan-petrov.png',     'dev_sn': 9001, 'dev_name': 'Tracker Ivan'},
    {'first_name': 'Maria',  'last_name': 'Georgieva', 'phone': '+359888000002', 'pin': '2345',
     'username': 'demo_maria',    'rank': 'Corporal',   'blood_type': 'B+',
     'photo': 'maria-georgieva.png', 'dev_sn': 9002, 'dev_name': 'Tracker Maria'},
    {'first_name': 'Georgi', 'last_name': 'Dimitrov',  'phone': '+359888000003', 'pin': '3456',
     'username': 'demo_georgi',   'rank': 'Lieutenant', 'blood_type': 'O+',
     'photo': 'georgi-dimitrov.png', 'dev_sn': 9003, 'dev_name': 'Tracker Georgi'},
    {'first_name': 'Elena',  'last_name': 'Stoyanova', 'phone': '+359888000004', 'pin': '4567',
     'username': 'demo_elena',    'rank': 'Private',    'blood_type': 'AB-',
     'photo': 'elena-stoyanova.png', 'dev_sn': 9004, 'dev_name': 'Tracker Elena'},
    {'first_name': 'Bai',    'last_name': 'Ivan',      'phone': '+359888000005', 'pin': '5678',
     'username': 'demo_bai_ivan', 'rank': None,         'blood_type': None,
     'photo': 'bai-ivan.png',        'dev_sn': 9005, 'dev_name': 'Tracker Bai Ivan'},
    {'first_name': 'Kiril',  'last_name': 'Iliev',     'phone': '+359888000006', 'pin': '6789',
     'username': 'demo_kiril',    'rank': None,         'blood_type': None,
     'photo': 'kiril-iliev.jpg',     'dev_sn': 9006, 'dev_name': 'Tracker Kiril'},
]

SOS_DEVICE = 'demo_elena'   # first to get the SOS role, like tools/demo.py

# Extra trackers beyond the six personas: no photo, no team (tests the "no team" display too)
DEMO_USERS += [
    {'first_name': 'Demo', 'last_name': f'Tracker {i:02d}', 'phone': f'+3598880000{i:02d}', 'pin': None,
     'username': f'demo_extra_{i:02d}', 'rank': None, 'blood_type': None,
     'photo': None, 'dev_sn': 9000 + i, 'dev_name': f'Tracker Demo {i:02d}'}
    for i in range(7, 13)
]
MAX_TRACKERS = len(DEMO_USERS)          # 12
DEMO_SNS = [u['dev_sn'] for u in DEMO_USERS]
STALE_AGE = timedelta(minutes=15)       # lib/freshness.js: stale after 10 min
LOST_AGE = timedelta(minutes=45)        # ... lost after 30 min

DEMO_GROUPS = [
    {'name': 'Alpha Team', 'description': 'First response unit', 'color': '#ef4444',
     'member_usernames': ['demo_ivan', 'demo_maria'], 'leader_username': 'demo_ivan'},
    {'name': 'Bravo Team', 'description': 'Support unit', 'color': '#3b82f6',
     'member_usernames': ['demo_georgi', 'demo_elena'], 'leader_username': 'demo_georgi'},
]


class SimulationRunning(Exception):
    pass


@dataclass(frozen=True)
class Scenario:
    trackers: int = 6
    sos: int = 1
    no_fix: int = 0
    stale: int = 0
    lost: int = 0
    low_battery: int = 0
    step_m: int = 300          # movement per update
    spread_km: float = 5.0     # start positions within this distance of the start point

    def roles(self, usernames: list[str]) -> dict[str, str]:
        """username -> sos | no_fix | stale | lost | moving. The SOS persona goes first, so the
        default scenario puts the same tracker in SOS as tools/demo.py."""
        order = sorted(usernames, key=lambda u: u != SOS_DEVICE)
        plan = ['sos'] * self.sos + ['no_fix'] * self.no_fix + ['stale'] * self.stale + ['lost'] * self.lost
        return {u: (plan[i] if i < len(plan) else 'moving') for i, u in enumerate(order)}


async def seed(conn: asyncpg.Connection, count: int = 6) -> dict[str, asyncpg.Record]:
    """Create or reuse the first `count` demo volunteers and trackers, and the teams of the personas
    among them. Returns username -> device {id, user_id}."""
    users = DEMO_USERS[:count]
    user_ids: dict[str, uuid.UUID] = {}
    async with conn.transaction():
        for u in users:
            row = await conn.fetchrow('SELECT id, is_active, photo_url FROM users WHERE username = $1', u['username'])
            if row is None:
                row = await conn.fetchrow(
                    """INSERT INTO users (username, password_hash, pin, first_name, last_name, full_name,
                                          phone, rank, blood_type, role)
                       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,'rescuer')
                       RETURNING id, is_active, photo_url""",
                    u['username'], hash_password(secrets.token_urlsafe(32)), u['pin'], u['first_name'],
                    u['last_name'], f"{u['first_name']} {u['last_name']}", u['phone'], u['rank'], u['blood_type'],
                )
            elif not row['is_active']:
                await conn.execute('UPDATE users SET is_active = TRUE WHERE id = $1', row['id'])
            user_ids[u['username']] = row['id']
            if not row['photo_url'] and u['photo']:
                photo_url = _copy_persona_photo(u['photo'])
                if photo_url:
                    await conn.execute('UPDATE users SET photo_url = $1 WHERE id = $2', photo_url, row['id'])

        devices: dict[str, asyncpg.Record] = {}
        for u in users:
            uid = user_ids[u['username']]
            dev = await conn.fetchrow('SELECT id, user_id, is_active FROM devices WHERE dev_sn = $1', u['dev_sn'])
            if dev is None:
                dev = await conn.fetchrow(
                    """INSERT INTO devices (dev_sn, name, device_type, user_id) VALUES ($1,$2,'bee',$3)
                       RETURNING id, user_id, is_active""",
                    u['dev_sn'], u['dev_name'], uid,
                )
            elif not dev['is_active'] or dev['user_id'] != uid:
                dev = await conn.fetchrow(
                    'UPDATE devices SET is_active = TRUE, user_id = $2 WHERE id = $1 RETURNING id, user_id, is_active',
                    dev['id'], uid,
                )
            devices[u['username']] = dev

        for g in DEMO_GROUPS:
            if not all(m in user_ids for m in g['member_usernames']):
                continue   # a team is only created once all its members are part of the scenario
            if await conn.fetchval('SELECT 1 FROM groups WHERE name = $1', g['name']):
                continue
            gid = await conn.fetchval(
                'INSERT INTO groups (name, description, color) VALUES ($1,$2,$3) RETURNING id',
                g['name'], g['description'], g['color'],
            )
            for uname in g['member_usernames']:
                await conn.execute(
                    """INSERT INTO user_groups (user_id, group_id, is_leader) VALUES ($1,$2,$3)
                       ON CONFLICT (user_id, group_id) DO UPDATE SET is_leader = EXCLUDED.is_leader""",
                    user_ids[uname], gid, uname == g['leader_username'],
                )
    return devices


async def reset(conn: asyncpg.Connection) -> dict:
    """Delete every position and SOS alert of the demo trackers. Accounts, devices and teams stay."""
    async with conn.transaction():
        ids = [r['id'] for r in await conn.fetch('SELECT id FROM devices WHERE dev_sn = ANY($1::int[])', DEMO_SNS)]
        positions = await conn.fetchval(
            'WITH d AS (DELETE FROM location_events WHERE device_id = ANY($1::uuid[]) RETURNING 1) SELECT count(*) FROM d', ids)
        alerts = await conn.fetchval(
            'WITH d AS (DELETE FROM sos_alerts WHERE device_id = ANY($1::uuid[]) RETURNING 1) SELECT count(*) FROM d', ids)
    return {'positions': positions, 'sos_alerts': alerts}


def _copy_persona_photo(name: str) -> str | None:
    """Copy a persona photo into uploads/ like POST /users/{id}/photo would. A missing file is skipped."""
    src = PERSONAS_DIR / name
    if not src.is_file():
        return None
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    filename = f'{uuid.uuid4()}{src.suffix.lower()}'
    shutil.copyfile(src, UPLOADS_DIR / filename)
    return f'/uploads/{filename}'


@dataclass
class Simulation:
    task: asyncio.Task | None = None
    started_at: datetime | None = None
    lat: float = 0.0
    lon: float = 0.0
    interval: float = 0.0
    scenario: Scenario = field(default_factory=Scenario)
    steps: int = 0
    devices: int = 0
    last_error: str | None = None
    _positions: dict = field(default_factory=dict)
    _roles: dict = field(default_factory=dict)
    _low_battery: set = field(default_factory=set)

    @property
    def running(self) -> bool:
        return self.task is not None and not self.task.done()

    def status(self) -> dict:
        return {
            'running':    self.running,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'lat':        self.lat,
            'lon':        self.lon,
            'interval':   self.interval,
            'scenario':   vars(self.scenario).copy(),
            'steps':      self.steps,
            'devices':    self.devices,
            'last_error': self.last_error,
        }

    async def start(self, lat: float, lon: float, interval: float, scenario: Scenario | None = None) -> dict:
        if self.running:
            raise SimulationRunning()
        scenario = scenario or Scenario()
        async with get_pool().acquire() as conn:
            devices = await seed(conn, scenario.trackers)
            self.lat, self.lon, self.interval, self.scenario = lat, lon, interval, scenario
            self.steps, self.devices, self.last_error = 0, len(devices), None
            self.started_at = datetime.now(timezone.utc)
            self._roles = scenario.roles(list(devices))
            self._low_battery = set(list(devices)[::-1][:scenario.low_battery])   # last trackers first
            # spread_km around the start point; a degree of longitude shrinks with latitude
            dlat = scenario.spread_km / 111.0
            dlon = scenario.spread_km / (111.0 * max(math.cos(math.radians(lat)), 0.01))
            self._positions = {u: (lat + random.uniform(-dlat, dlat), lon + random.uniform(-dlon, dlon)) for u in devices}
            # stale / lost: one report in the past, then silence
            for uname, age in (('stale', STALE_AGE), ('lost', LOST_AGE)):
                for u, role in self._roles.items():
                    if role == uname:
                        plat, plon = self._positions[u]
                        await record_position(conn, devices[u], round(plat, 6), round(plon, 6), False,
                                              battery=self._battery(u), at=self.started_at - age)
        self.task = asyncio.create_task(self._run(devices))
        logger.warning('Test mode STARTED: %d demo trackers around %.5f, %.5f every %ss (%s)',
                       len(devices), lat, lon, interval, scenario)
        return self.status()

    async def stop(self) -> dict:
        if self.task is not None:
            self.task.cancel()
            with suppress(asyncio.CancelledError):
                await self.task
            self.task = None
            logger.warning('Test mode stopped after %d steps', self.steps)
        return self.status()

    def _battery(self, uname: str) -> float:
        low = uname in self._low_battery
        return round(random.uniform(3.20, 3.40) if low else random.uniform(3.70, 4.20), 2)

    async def _run(self, devices: dict) -> None:
        step_deg = self.scenario.step_m / 111_000
        while True:
            try:
                async with get_pool().acquire() as conn:
                    for uname, device in devices.items():
                        role = self._roles.get(uname, 'moving')
                        if role in ('stale', 'lost'):
                            continue
                        plat, plon = self._positions[uname]
                        if role == 'no_fix' and self.steps > 0:
                            # in contact without a fix: the reader anchors such frames to the last fix
                            await record_position(conn, device, round(plat, 6), round(plon, 6), False,
                                                  gnss_valid=False, battery=self._battery(uname))
                            continue
                        if self.steps > 0:
                            plat += random.uniform(-step_deg, step_deg)
                            plon += random.uniform(-step_deg, step_deg) / max(math.cos(math.radians(plat)), 0.01)
                            self._positions[uname] = (plat, plon)
                        await record_position(conn, device, round(plat, 6), round(plon, 6), role == 'sos',
                                              battery=self._battery(uname))
                self.steps += 1
                self.last_error = None
            except asyncio.CancelledError:
                raise
            except Exception as exc:   # keep simulating through a DB hiccup; the UI shows the last error
                self.last_error = str(exc) or type(exc).__name__
                logger.warning('Test mode step failed: %s', exc)
            await asyncio.sleep(self.interval)


simulation = Simulation()
