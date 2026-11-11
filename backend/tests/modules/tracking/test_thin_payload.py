"""T547: the live messages of tracking and sos, with and without the personal fields.

LIVE_PERSONAL_FIELDS=true (the default) sends today's messages byte for byte; false sends ids and position
data only. The literals below were recorded from the code BEFORE T547 (same frozen clock, same fakes).
"""
import dataclasses
import json
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from backend.config import settings
from backend.core.config import Settings
from backend.hardware_reader import reader
from backend.modules.tracking import api as tracking_api
from backend.routers import test as sim_route
from backend.tests.modules.gateway import delegates_helper as H
from backend.tests.modules.gateway.gateway_fakes import install

pytestmark = pytest.mark.Trait("Task", "T547")

GROUPS = [{'id': 'g1', 'name': 'Alpha', 'color': '#f00', 'is_leader': True}]

# location_update of a plain fix, a rising SOS (both messages of one frame) and the simulation: recorded from the
# unchanged code. Strings, not dicts: the key ORDER is part of "byte for byte".
TODAY_FIX = (
    '{"device_id": "dev-uuid-1", "user_id": "user-uuid-1", "full_name": "Ivan Petrov", "rank": "Sgt", '
    '"photo_url": null, "phone": "+359", "mgrs": "35TNH1234567890", "latitude": 42.1438409, '
    '"longitude": 24.7495615, "altitude_m": 200, "speed_knots": 5.0, "course_deg": 137, "battery_voltage": 3.7, '
    '"gnss_satellites": 12, "gnss_valid": true, "sos_active": false, "repeater_mode": false, '
    '"recorded_at": "2024-12-08T20:50:05+00:00", "received_at": "2024-12-08T21:00:00+00:00", '
    '"groups": [{"id": "g1", "name": "Alpha", "color": "#f00", "is_leader": true}]}')
TODAY_SOS_ALERT = (
    '{"id": "alert-uuid-1", "device_id": "dev-uuid-1", "user_id": "user-uuid-1", "dev_sn": 1235, '
    '"full_name": "Ivan Petrov", "rank": "Sgt", "triggered_at": "2024-12-08T20:50:05+00:00"}')
TODAY_SOS_FIX = TODAY_FIX.replace('"sos_active": false', '"sos_active": true')
TODAY_SIMULATED = (
    '{"device_id": "dev-uuid-1", "user_id": "user-uuid-1", "full_name": "Ivan Petrov", "rank": "Sgt", '
    '"photo_url": null, "phone": "+359", "mgrs": "34TFN8838230066", "latitude": 42.7, "longitude": 23.3, '
    '"altitude_m": 100, "speed_knots": 5.0, "battery_voltage": 5.0, "gnss_satellites": 100, "gnss_valid": true, '
    '"sos_active": false, "repeater_mode": false, "recorded_at": "2024-12-08T21:00:00+00:00", '
    '"received_at": "2024-12-08T21:00:00+00:00", '
    '"groups": [{"id": "g1", "name": "Alpha", "color": "#f00", "is_leader": true}]}')

THIN_LOCATION = ['device_id', 'user_id', 'mgrs', 'latitude', 'longitude', 'altitude_m', 'speed_knots', 'course_deg',
                 'battery_voltage', 'gnss_satellites', 'gnss_valid', 'sos_active', 'repeater_mode', 'recorded_at',
                 'received_at']
THIN_SOS = ['id', 'device_id', 'user_id', 'dev_sn', 'triggered_at']


@pytest.fixture
def thin(monkeypatch):
    monkeypatch.setattr(settings, 'live_personal_fields', False)


class _Run:
    def __init__(self, conn, calls):
        self.conn, self.calls = conn, calls

    def sent(self, channel):
        return [c.args[1] for c in self.conn.execute.call_args_list if f"pg_notify('{channel}'" in c.args[0]]

    @property
    def sql(self):
        return [' '.join(sql.split()) for _, sql, _ in self.calls]


async def _reader(name, monkeypatch, **state_over):
    kind, frame, state = H.CASES[name]
    conn = AsyncMock()
    routed = install(conn, **{**state, 'groups': GROUPS, **state_over})
    calls = []

    def record(method):
        async def call(sql, *args):
            calls.append((method, sql, args))
            return getattr(routed, method)(sql, *args)
        return call

    for method in ('fetchrow', 'fetchval', 'fetch'):
        setattr(conn, method, record(method))
    conn.execute = AsyncMock(side_effect=lambda sql, *a: calls.append(('execute', sql, a)))

    class Frozen(H.datetime):
        @classmethod
        def now(cls, tz=None):
            return H.FROZEN

    monkeypatch.setattr(reader, 'datetime', Frozen)
    await reader._handle_bee(frame, conn)
    return _Run(conn, calls)


async def _simulate(monkeypatch, user=None, **kw):
    user = H.USER if user is None else user
    monkeypatch.setattr(sim_route.random, 'randint', lambda a, b: 100)
    monkeypatch.setattr(sim_route.random, 'uniform', lambda a, b: 5.0)
    calls = []
    conn = AsyncMock()

    async def fetchrow(sql, *a):
        calls.append(('fetchrow', sql, a))
        if 'INSERT' in sql:
            return {'id': 'ev-1'}
        if 'FROM users' in sql or 'is_active' in sql:
            return user

    async def fetch(sql, *a):
        calls.append(('fetch', sql, a))
        return GROUPS

    conn.fetchrow, conn.fetch, conn.execute = fetchrow, fetch, AsyncMock()
    try:
        await sim_route.record_position(conn, H.DEVICE, 42.7, 23.3, False, at=H.FROZEN, **kw)
    finally:
        run = _Run(conn, calls)
    return run


# ── default mode: today's messages, byte for byte ────────────────────────────

@pytest.mark.asyncio
async def test_the_default_is_the_full_payload():
    assert Settings.model_fields['live_personal_fields'].default is True


@pytest.mark.asyncio
async def test_default_reader_fix_is_todays_message(monkeypatch):
    run = await _reader('fix', monkeypatch)
    assert run.sent('location_update') == [TODAY_FIX]
    assert run.sent('sos_alert') == []


@pytest.mark.asyncio
async def test_default_reader_rising_sos_is_todays_two_messages(monkeypatch):
    run = await _reader('rising_sos', monkeypatch)
    assert run.sent('sos_alert') == [TODAY_SOS_ALERT]
    assert run.sent('location_update') == [TODAY_SOS_FIX]


@pytest.mark.asyncio
async def test_default_simulate_is_todays_message(monkeypatch):
    run = await _simulate(monkeypatch)
    assert run.sent('location_update') == [TODAY_SIMULATED]
    assert len(json.loads(TODAY_SIMULATED)) == 19


@pytest.mark.asyncio
async def test_default_still_reads_names_and_teams(monkeypatch):
    run = await _reader('fix', monkeypatch)
    assert any('FROM user_groups' in s for s in run.sql) and any('full_name' in s for s in run.sql)


# ── the switch and the key set ────────────────────────────────────────────────

def test_personal_keys_are_the_fields_of_personal_details():
    from backend.modules.tracking.domain.payload import PersonalDetails
    assert tracking_api.PERSONAL_KEYS == frozenset(f.name for f in dataclasses.fields(PersonalDetails))
    assert tracking_api.PERSONAL_KEYS == {'full_name', 'rank', 'photo_url', 'phone', 'groups'}
    # a message that carries the whole personal part has exactly these keys beyond the position data
    assert set(json.loads(TODAY_FIX)) - set(THIN_LOCATION) == tracking_api.PERSONAL_KEYS


@pytest.mark.asyncio
async def test_the_switch_is_read_per_call_not_at_import(monkeypatch):
    monkeypatch.setattr(settings, 'live_personal_fields', False)
    assert list(json.loads((await _reader('fix', monkeypatch)).sent('location_update')[0])) == THIN_LOCATION
    monkeypatch.setattr(settings, 'live_personal_fields', True)
    assert (await _reader('fix', monkeypatch)).sent('location_update') == [TODAY_FIX]


# ── thin mode (LIVE_PERSONAL_FIELDS=false): the plan's tests ──────────────────

@pytest.mark.asyncio
async def test_location_update_has_exactly_the_thin_keys(thin, monkeypatch):
    run = await _reader('fix', monkeypatch)
    [text] = run.sent('location_update')
    assert list(json.loads(text)) == THIN_LOCATION and len(json.loads(text)) == 15


@pytest.mark.asyncio
async def test_sos_alert_has_exactly_the_thin_keys(thin, monkeypatch):
    run = await _reader('rising_sos', monkeypatch)
    [text] = run.sent('sos_alert')
    body = json.loads(text)
    assert list(body) == THIN_SOS and len(body) == 5 and isinstance(body['id'], str)


@pytest.mark.asyncio
async def test_the_reader_path_sends_exactly_the_thin_keys(thin, monkeypatch):
    run = await _reader('rising_sos', monkeypatch)
    assert [list(json.loads(t)) for t in run.sent('sos_alert')] == [THIN_SOS]
    assert [list(json.loads(t)) for t in run.sent('location_update')] == [THIN_LOCATION]


@pytest.mark.asyncio
async def test_the_simulation_sends_the_thin_keys_without_course(thin, monkeypatch):
    run = await _simulate(monkeypatch)
    [text] = run.sent('location_update')
    assert list(json.loads(text)) == [k for k in THIN_LOCATION if k != 'course_deg']


@pytest.mark.asyncio
async def test_no_live_message_of_tracking_or_sos_carries_a_personal_key(thin, monkeypatch):
    runs = [await _reader('fix', monkeypatch), await _reader('rising_sos', monkeypatch),
            await _simulate(monkeypatch)]
    messages = [t for r in runs for ch in ('location_update', 'sos_alert') for t in r.sent(ch)]
    assert len(messages) == 4
    for text in messages:
        assert not tracking_api.PERSONAL_KEYS & set(json.loads(text)), text


@pytest.mark.asyncio
async def test_the_teams_and_name_reads_are_gone(thin, monkeypatch):
    for run in (await _reader('fix', monkeypatch), await _reader('rising_sos', monkeypatch),
                await _simulate(monkeypatch)):
        for sql in run.sql:
            assert 'FROM user_groups' not in sql and 'full_name' not in sql, sql
        assert any('is_active FROM users' in s for s in run.sql)


@pytest.mark.asyncio
@pytest.mark.parametrize('thin_mode', [False, True])
async def test_an_inactive_person_is_still_not_broadcast(monkeypatch, thin_mode):
    monkeypatch.setattr(settings, 'live_personal_fields', not thin_mode)
    inactive = {**H.USER, 'is_active': False}
    run = await _reader('inactive_person', monkeypatch, user=inactive)
    assert run.sent('location_update') == []
    assert any('INSERT INTO location_events' in s for s in run.sql)          # stored, not broadcast
    with pytest.raises(HTTPException) as err:
        await _simulate(monkeypatch, user=inactive)
    assert err.value.status_code == 400


def test_rest_still_returns_the_names(thin, client, mock_conn):
    mock_conn.fetch = AsyncMock(return_value=[{'device_id': 'd1', 'full_name': 'Ivan Petrov', 'groups': '[]'}])
    assert client.get('/api/locations/live').json()[0]['full_name'] == 'Ivan Petrov'
    mock_conn.fetch = AsyncMock(return_value=[{'id': 'a1', 'full_name': 'Ivan Petrov', 'rank': 'Sgt'}])
    assert client.get('/api/locations/sos').json()[0]['full_name'] == 'Ivan Petrov'
