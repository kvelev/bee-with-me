"""T541: `tracking.api` is how positions are written outside the hardware reader."""
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.modules.tracking import api
from backend.modules.tracking.infrastructure import repository
from backend.tests.architecture import sql_scan

REPO = Path(__file__).resolve().parents[4]

pytestmark = pytest.mark.Trait("Task", "T541")

KEYS = ['device_id', 'user_id', 'full_name', 'rank', 'photo_url', 'phone', 'mgrs', 'latitude', 'longitude',
        'altitude_m', 'speed_knots', 'course_deg', 'battery_voltage', 'gnss_satellites', 'gnss_valid',
        'sos_active', 'repeater_mode', 'recorded_at', 'received_at', 'groups']


def _payload(roster):
    when = datetime(2026, 11, 1, 10, 0, tzinfo=timezone.utc)
    return api.location_update_payload(
        device_id=uuid.uuid4(), user_id=uuid.uuid4(), roster=roster, groups=[], mgrs='35TLH1234', latitude=42.0,
        longitude=25.0, altitude_m=10, speed_knots=1.5, course_deg=90, battery_voltage=3.9, gnss_satellites=7,
        gnss_valid=True, sos_active=False, repeater_mode=False, recorded_at=when, received_at=when)


@pytest.mark.Trait("Task", "T541")
def test_payload_has_todays_keys_in_todays_order():
    roster = {'full_name': 'Ivan', 'rank': 'Sgt', 'photo_url': '/uploads/a.jpg', 'phone': '1'}
    out = _payload(roster)
    assert list(out) == KEYS
    assert out['full_name'] == 'Ivan' and out['recorded_at'] == '2026-11-01T10:00:00+00:00'
    none = _payload(None)
    assert list(none) == KEYS
    assert [none[k] for k in ('full_name', 'rank', 'photo_url', 'phone')] == [None] * 4


INSERT_ARGS = {'device_id': 'd', 'user_id': 'u', 'msg_id': 1, 'at': 'a', 'latitude': 1.0, 'longitude': 2.0,
               'mgrs': 'm', 'altitude_m': 3, 'speed_knots': 4.0, 'gnss_satellites': 5, 'battery_voltage': 3.7,
               'sos_active': False, 'gnss_valid': True}
PASS_THROUGH = {
    'insert_simulated_position': INSERT_ARGS,
    'person_of': ('u',), 'groups_of': ('u',), 'publish_position': ({'a': 1},),
    'forget_person': ('u',), 'delete_device_positions': ('d',), 'delete_device_heartbeats': ('d',),
    'delete_positions_of_devices': (['d'],),
}


@pytest.mark.Trait("Task", "T541")
@pytest.mark.asyncio
@pytest.mark.parametrize('name', sorted(PASS_THROUGH))
async def test_api_looks_the_implementation_up_at_call_time(monkeypatch, name):
    seen = []

    async def fake(*args, **kwargs):
        seen.append((args, kwargs))
        return 'marker'

    monkeypatch.setattr(repository, name, fake)
    spec = PASS_THROUGH[name]
    if isinstance(spec, dict):
        assert await getattr(api, name)('conn', **spec) == 'marker'
        assert seen == [(('conn',), spec)]
    else:
        assert await getattr(api, name)('conn', *spec) == 'marker'
        assert seen == [(('conn', *spec), {})]


def _conn():
    conn = MagicMock()
    conn.transaction = MagicMock()
    conn.execute = AsyncMock(return_value='DELETE 2')
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchrow = AsyncMock(return_value={'id': uuid.uuid4()})
    conn.fetchval = AsyncMock(return_value=2)
    return conn


@pytest.mark.Trait("Task", "T541")
@pytest.mark.asyncio
async def test_each_command_runs_on_the_callers_connection_without_a_transaction():
    conn = _conn()
    when = datetime(2026, 11, 1, tzinfo=timezone.utc)
    await api.insert_simulated_position(conn, **{**INSERT_ARGS, 'at': when})
    await api.person_of(conn, 'u')
    await api.groups_of(conn, 'u')
    await api.publish_position(conn, {'a': 1})
    await api.forget_person(conn, 'u')
    await api.delete_device_positions(conn, 'd')
    await api.delete_device_heartbeats(conn, 'd')
    await api.delete_positions_of_devices(conn, ['d'])
    conn.transaction.assert_not_called()
    used = conn.execute.await_count + conn.fetch.await_count + conn.fetchrow.await_count + conn.fetchval.await_count
    assert used == 8


@pytest.mark.Trait("Task", "T541")
@pytest.mark.asyncio
async def test_publish_sends_one_notify_on_the_location_channel():
    conn = _conn()
    await api.publish_position(conn, {'device_id': 'x', 'n': 1})
    conn.execute.assert_awaited_once()
    sql, text = conn.execute.await_args.args
    assert "pg_notify('location_update'" in sql
    assert json.loads(text) == {'device_id': 'x', 'n': 1}


@pytest.mark.Trait("Task", "T541")
def test_deleting_a_device_keeps_the_order_alerts_positions_heartbeats(client, mock_conn):
    calls = []

    async def run(sql, *args):
        calls.append(sql)
        return 'DELETE 0'

    async def fetch(sql, *args):
        calls.append(sql)
        return []

    async def fetchval(sql, *args):
        calls.append(sql)
        return uuid.uuid4()

    mock_conn.execute, mock_conn.fetch, mock_conn.fetchval = run, fetch, fetchval
    assert client.delete(f'/api/devices/{uuid.uuid4()}/permanent').status_code == 204
    needles = ['FROM sos_alerts', 'FROM location_events', 'FROM repeater_events', 'pg_advisory_xact_lock']
    at = [next(i for i, sql in enumerate(calls) if n in sql) for n in needles]
    assert at == sorted(at) and len(set(at)) == 4


@pytest.mark.Trait("Task", "T541")
def test_no_writer_outside_the_modules_is_left():
    allowed = ('modules/tracking/infrastructure/repository.py', 'modules/sos/infrastructure/repository.py',
               'hardware_reader/reader.py', 'main.py')
    found = {(str(p).replace('\\', '/'), t, v) for p, t, v in sql_scan.scan_writes(REPO / 'backend')
             if t in ('location_events', 'repeater_events', 'sos_alerts')}
    stray = {row for row in found if not row[0].endswith(allowed)}
    assert not stray, stray
