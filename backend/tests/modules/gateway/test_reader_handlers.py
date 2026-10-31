"""Characterisation of the gateway frame handlers (reader.py). Mocked connection, no Postgres."""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from backend.hardware_reader.parser import BeeFrame, RepeaterFrame
from backend.hardware_reader.reader import _handle_bee, _handle_repeater

pytestmark = [pytest.mark.Trait("Task", "T114"), pytest.mark.asyncio]

DEVICE = {'id': 'dev-uuid-1', 'user_id': 'user-uuid-1'}
USER = {'full_name': 'Ivan Petrov', 'rank': 'Sgt', 'photo_url': None, 'phone': '+359', 'is_active': True}
RECORDED = datetime(2024, 12, 8, 20, 50, 5, tzinfo=timezone.utc)

LOCATION_KEYS = {
    'device_id', 'user_id', 'full_name', 'rank', 'photo_url', 'phone', 'mgrs', 'latitude',
    'longitude', 'altitude_m', 'speed_knots', 'course_deg', 'battery_voltage', 'gnss_satellites',
    'gnss_valid', 'sos_active', 'repeater_mode', 'recorded_at', 'received_at', 'groups',
}
SOS_KEYS = {'id', 'device_id', 'user_id', 'dev_sn', 'full_name', 'rank', 'triggered_at'}


def bee_frame(**over) -> BeeFrame:
    fields = dict(
        msg_id=2, dev_sn=1235, recorded_at=RECORDED, gnss_valid=True,
        latitude=42.1438409, longitude=24.7495615, mgrs='35TNH1234567890',
        speed_knots=5.0, course_deg=137, gnss_satellites=12, altitude_m=200,
        battery_voltage=3.7, sos_active=False, repeater_mode=False, raw_flags=0, event_id=884,
    )
    fields.update(over)
    return BeeFrame(**fields)


def sql_calls(mock, fragment):
    return [c for c in mock.call_args_list if fragment in c.args[0]]


def notifies(conn, channel):
    out = []
    for c in conn.execute.call_args_list:
        if f"pg_notify('{channel}'" in c.args[0]:
            out.append(json.loads(c.args[1]))
    return out


async def test_unknown_device_stores_nothing(mock_conn):
    await _handle_bee(bee_frame(), mock_conn)

    assert mock_conn.execute.call_count == 0
    assert mock_conn.fetchrow.call_count == 1
    assert mock_conn.fetchrow.call_args.args[1:] == (1235, 'bee')


async def test_no_fix_frame_without_previous_fix_is_dropped(mock_conn):
    mock_conn.fetchrow = AsyncMock(side_effect=[DEVICE, None])

    await _handle_bee(bee_frame(gnss_valid=False), mock_conn)

    last_fix_call = mock_conn.fetchrow.call_args_list[1]
    assert 'gnss_valid = TRUE' in last_fix_call.args[0]
    assert last_fix_call.args[1] == 'dev-uuid-1'
    assert sql_calls(mock_conn.execute, 'INSERT INTO location_events') == []
    assert mock_conn.execute.call_count == 0


async def test_no_fix_frame_reuses_last_fix(mock_conn):
    last_fix = {'latitude': 42.1, 'longitude': 24.1, 'mgrs': '35TNH0000000000'}
    mock_conn.fetchrow = AsyncMock(side_effect=[DEVICE, last_fix, USER])
    mock_conn.fetchval = AsyncMock(side_effect=[False, False])

    await _handle_bee(bee_frame(gnss_valid=False, latitude=0.0, longitude=0.0, mgrs=''), mock_conn)

    inserts = sql_calls(mock_conn.execute, 'INSERT INTO location_events')
    assert len(inserts) == 1
    args = inserts[0].args
    # args[0] is the SQL text; $6 latitude, $7 longitude, $8 mgrs; the last parameter is gnss_valid
    assert args[6:9] == (42.1, 24.1, '35TNH0000000000')
    assert args[-1] is False
    payload = notifies(mock_conn, 'location_update')[0]
    assert (payload['latitude'], payload['longitude'], payload['gnss_valid']) == (42.1, 24.1, False)


async def test_sos_edge_opens_alert_once(mock_conn):
    alert = {'id': 'alert-uuid-1', 'triggered_at': RECORDED}
    # fetchrow order: device, existing-open-alert check, INSERT sos_alerts RETURNING, who, user row
    mock_conn.fetchrow = AsyncMock(side_effect=[DEVICE, None, alert, USER, USER])
    mock_conn.fetchval = AsyncMock(side_effect=[False, True])

    await _handle_bee(bee_frame(sos_active=True), mock_conn)

    assert len(sql_calls(mock_conn.fetchrow, 'INSERT INTO sos_alerts')) == 1
    sos = notifies(mock_conn, 'sos_alert')
    assert len(sos) == 1
    assert set(sos[0]) == SOS_KEYS
    assert sos[0]['id'] == 'alert-uuid-1'
    assert sos[0]['dev_sn'] == 1235
    assert sos[0]['full_name'] == 'Ivan Petrov'
    assert sos[0]['triggered_at'] == RECORDED.isoformat()

    # The device keeps asserting SOS: previous state already True -> no new alert
    conn2 = AsyncMock()
    conn2.fetchrow = AsyncMock(side_effect=[DEVICE, USER])
    conn2.fetch = AsyncMock(return_value=[])
    conn2.execute = AsyncMock(return_value=None)
    conn2.fetchval = AsyncMock(side_effect=[True, True])

    await _handle_bee(bee_frame(sos_active=True), conn2)

    assert sql_calls(conn2.fetchrow, 'INSERT INTO sos_alerts') == []
    assert notifies(conn2, 'sos_alert') == []


async def test_location_update_payload_shape(mock_conn):
    group = {'id': 'g-uuid-1', 'name': 'Alpha', 'color': '#ff0', 'is_leader': True}
    mock_conn.fetchrow = AsyncMock(side_effect=[DEVICE, USER])
    mock_conn.fetch = AsyncMock(return_value=[group])
    # raw flag False, but an unresolved alert exists: the broadcast must say sos_active True
    mock_conn.fetchval = AsyncMock(side_effect=[False, True])

    await _handle_bee(bee_frame(sos_active=False), mock_conn)

    payloads = notifies(mock_conn, 'location_update')
    assert len(payloads) == 1
    p = payloads[0]
    assert set(p) == LOCATION_KEYS
    assert len(p) == 20
    assert p['sos_active'] is True
    assert p['device_id'] == 'dev-uuid-1'
    assert p['full_name'] == 'Ivan Petrov'
    assert p['groups'] == [{'id': 'g-uuid-1', 'name': 'Alpha', 'color': '#ff0', 'is_leader': True}]
    assert p['recorded_at'] == RECORDED.isoformat()
    assert mock_conn.fetchrow.call_args_list[0].args[1:] == (1235, 'bee')


async def test_inactive_user_frame_is_stored_but_not_broadcast(mock_conn):
    inactive = dict(USER, is_active=False)
    mock_conn.fetchrow = AsyncMock(side_effect=[DEVICE, inactive])
    mock_conn.fetchval = AsyncMock(side_effect=[False, False])

    await _handle_bee(bee_frame(), mock_conn)

    assert len(sql_calls(mock_conn.execute, 'INSERT INTO location_events')) == 1
    assert notifies(mock_conn, 'location_update') == []
    assert sql_calls(mock_conn.execute, 'pg_notify') == []


async def test_repeater_frame_inserts_heartbeat(mock_conn):
    mock_conn.fetchrow = AsyncMock(return_value={'id': 'rep-uuid-1', 'user_id': None})

    await _handle_repeater(RepeaterFrame(msg_id=100, dev_sn=1256, battery_voltage=3.4, event_id=412), mock_conn)

    assert mock_conn.fetchrow.call_args.args[1:] == (1256, 'repeater')
    inserts = sql_calls(mock_conn.execute, 'INSERT INTO repeater_events')
    assert len(inserts) == 1
    assert inserts[0].args[1:] == ('rep-uuid-1', 100, 3.4)
