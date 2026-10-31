"""Characterisation of the gateway frame handlers (reader.py). Mocked connection, no Postgres.

Every query is answered by its SQL text (gateway_fakes.install), never by call order, so the tests
survive a reordering of the statements (step 3 moves them into one transaction)."""

import json
from datetime import datetime, timezone

import pytest

from backend.hardware_reader.parser import BeeFrame, RepeaterFrame
from backend.hardware_reader.reader import _handle_bee, _handle_repeater
from backend.tests.modules.gateway.gateway_fakes import install

pytestmark = [pytest.mark.Trait("Task", "T114"), pytest.mark.asyncio]

DEVICE = {'id': 'dev-uuid-1', 'user_id': 'user-uuid-1'}
USER = {'full_name': 'Ivan Petrov', 'rank': 'Sgt', 'photo_url': None, 'phone': '+359', 'is_active': True}
RECORDED = datetime(2024, 12, 8, 20, 50, 5, tzinfo=timezone.utc)
ALERT = {'id': 'alert-uuid-1', 'triggered_at': RECORDED}
OPEN_ALERT = {'id': 'alert-uuid-0'}

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
    install(mock_conn, device=None)

    await _handle_bee(bee_frame(), mock_conn)

    assert mock_conn.execute.call_count == 0
    device_lookups = sql_calls(mock_conn.fetchrow, 'FROM devices')
    assert len(device_lookups) == 1
    assert device_lookups[0].args[1:] == (1235, 'bee')


async def test_no_fix_frame_without_previous_fix_is_dropped(mock_conn):
    install(mock_conn, device=DEVICE, last_fix=None, prev_sos=False, user=USER)

    await _handle_bee(bee_frame(gnss_valid=False), mock_conn)

    last_fix_calls = sql_calls(mock_conn.fetchrow, 'gnss_valid = TRUE')
    assert len(last_fix_calls) == 1
    assert last_fix_calls[0].args[1] == 'dev-uuid-1'
    assert sql_calls(mock_conn.execute, 'INSERT INTO location_events') == []
    assert mock_conn.execute.call_count == 0


async def test_no_fix_frame_reuses_last_fix(mock_conn):
    last_fix = {'latitude': 42.1, 'longitude': 24.1, 'mgrs': '35TNH0000000000'}
    install(mock_conn, device=DEVICE, last_fix=last_fix, prev_sos=False, user=USER)

    await _handle_bee(bee_frame(gnss_valid=False, latitude=0.0, longitude=0.0, mgrs=''), mock_conn)

    inserts = sql_calls(mock_conn.execute, 'INSERT INTO location_events')
    assert len(inserts) == 1
    args = inserts[0].args
    # args[0] is the SQL text; $6 latitude, $7 longitude, $8 mgrs; the last parameter is gnss_valid
    assert args[6:9] == (42.1, 24.1, '35TNH0000000000')
    assert args[-1] is False
    payload = notifies(mock_conn, 'location_update')[0]
    assert (payload['latitude'], payload['longitude'], payload['gnss_valid']) == (42.1, 24.1, False)


async def test_sos_edge_opens_alert_and_announces_it(mock_conn):
    # previous frame had no SOS, no alert open: the FALSE -> TRUE edge opens exactly one alert
    sql = install(mock_conn, device=DEVICE, prev_sos=False, existing_alert=None, alert=ALERT, user=USER)

    await _handle_bee(bee_frame(sos_active=True, raw_flags=2), mock_conn)

    inserts = sql_calls(mock_conn.fetchrow, 'INSERT INTO sos_alerts')
    assert len(inserts) == 1
    assert inserts[0].args[1:] == ('dev-uuid-1', 'user-uuid-1', RECORDED)
    assert sql.alerts_inserted == 1
    sos = notifies(mock_conn, 'sos_alert')
    assert len(sos) == 1
    assert set(sos[0]) == SOS_KEYS
    assert sos[0]['id'] == 'alert-uuid-1'
    assert sos[0]['device_id'] == 'dev-uuid-1'
    assert sos[0]['user_id'] == 'user-uuid-1'
    assert sos[0]['dev_sn'] == 1235
    assert sos[0]['full_name'] == 'Ivan Petrov'
    assert sos[0]['rank'] == 'Sgt'
    assert sos[0]['triggered_at'] == RECORDED.isoformat()
    # the position push of the same frame shows the alert as open
    assert notifies(mock_conn, 'location_update')[0]['sos_active'] is True


async def test_sos_held_does_not_open_a_second_alert(mock_conn):
    # the device keeps asserting SOS: previous frame already True and the alert is still open
    sql = install(mock_conn, device=DEVICE, prev_sos=True, existing_alert=OPEN_ALERT, alert=ALERT, user=USER)

    await _handle_bee(bee_frame(sos_active=True, raw_flags=2), mock_conn)

    assert sql_calls(mock_conn.fetchrow, 'INSERT INTO sos_alerts') == []
    assert sql.alerts_inserted == 0
    assert notifies(mock_conn, 'sos_alert') == []
    assert len(sql_calls(mock_conn.execute, 'INSERT INTO location_events')) == 1
    assert notifies(mock_conn, 'location_update')[0]['sos_active'] is True


async def test_sos_edge_with_an_alert_already_open_does_not_duplicate_it(mock_conn):
    # FALSE -> TRUE edge, but an alert from an earlier press is still unresolved: no second alert
    sql = install(mock_conn, device=DEVICE, prev_sos=False, existing_alert=OPEN_ALERT, alert=ALERT, user=USER)

    await _handle_bee(bee_frame(sos_active=True, raw_flags=2), mock_conn)

    existing_checks = sql_calls(mock_conn.fetchrow, 'SELECT id FROM sos_alerts')
    assert len(existing_checks) == 1
    assert existing_checks[0].args[1] == 'dev-uuid-1'
    assert sql.alerts_inserted == 0
    assert notifies(mock_conn, 'sos_alert') == []


async def test_resolved_sos_does_not_light_up_again(mock_conn):
    # reader.py:135-144: the operator resolved the alert, the device still asserts SOS (raw flag True,
    # previous frame True). No new alert, and the push carries the effective state: sos_active False.
    sql = install(mock_conn, device=DEVICE, prev_sos=True, existing_alert=None, alert=ALERT, user=USER)

    await _handle_bee(bee_frame(sos_active=True, raw_flags=2), mock_conn)

    assert sql.alerts_inserted == 0
    assert notifies(mock_conn, 'sos_alert') == []
    inserts = sql_calls(mock_conn.execute, 'INSERT INTO location_events')
    assert len(inserts) == 1
    assert inserts[0].args[14] is True  # $14 sos_active: the raw flag is still stored
    payloads = notifies(mock_conn, 'location_update')
    assert len(payloads) == 1
    assert payloads[0]['sos_active'] is False


async def test_location_update_payload_shape(mock_conn):
    group = {'id': 'g-uuid-1', 'name': 'Alpha', 'color': '#ff0', 'is_leader': True}
    # raw flag False, but an unresolved alert exists: the broadcast must say sos_active True
    install(mock_conn, device=DEVICE, prev_sos=False, existing_alert=OPEN_ALERT, user=USER, groups=[group])

    await _handle_bee(bee_frame(sos_active=False), mock_conn)

    payloads = notifies(mock_conn, 'location_update')
    assert len(payloads) == 1
    p = payloads[0]
    assert set(p) == LOCATION_KEYS
    assert len(p) == 20
    assert p['sos_active'] is True
    assert p['device_id'] == 'dev-uuid-1'
    assert p['user_id'] == 'user-uuid-1'
    assert p['full_name'] == 'Ivan Petrov'
    assert p['groups'] == [{'id': 'g-uuid-1', 'name': 'Alpha', 'color': '#ff0', 'is_leader': True}]
    assert p['recorded_at'] == RECORDED.isoformat()
    assert sql_calls(mock_conn.fetchrow, 'FROM devices')[0].args[1:] == (1235, 'bee')
    assert sql_calls(mock_conn.fetch, 'FROM user_groups')[0].args[1] == 'user-uuid-1'


async def test_inactive_user_frame_is_stored_but_not_broadcast(mock_conn):
    inactive = dict(USER, is_active=False)
    install(mock_conn, device=DEVICE, prev_sos=False, user=inactive)

    await _handle_bee(bee_frame(), mock_conn)

    assert len(sql_calls(mock_conn.execute, 'INSERT INTO location_events')) == 1
    assert notifies(mock_conn, 'location_update') == []
    assert sql_calls(mock_conn.execute, 'pg_notify') == []


async def test_repeater_frame_inserts_heartbeat(mock_conn):
    install(mock_conn, device={'id': 'rep-uuid-1', 'user_id': None})

    await _handle_repeater(RepeaterFrame(msg_id=100, dev_sn=1256, battery_voltage=3.4, event_id=412), mock_conn)

    assert sql_calls(mock_conn.fetchrow, 'FROM devices')[0].args[1:] == (1256, 'repeater')
    inserts = sql_calls(mock_conn.execute, 'INSERT INTO repeater_events')
    assert len(inserts) == 1
    assert inserts[0].args[1:] == ('rep-uuid-1', 100, 3.4)


# ── fix round 2: pin the meaning, not only the shape ─────────────────────────

async def test_insert_args_and_full_payload_pin_clocks_and_columns(mock_conn):
    group = {'id': 'g-uuid-1', 'name': 'Alpha', 'color': '#ff0', 'is_leader': True}
    install(mock_conn, device=DEVICE, prev_sos=False, existing_alert=None, user=USER, groups=[group])
    frame = bee_frame(raw_flags=5, speed_knots=7.5, course_deg=211, battery_voltage=3.9, altitude_m=321,
                      gnss_satellites=9, repeater_mode=True)

    before = datetime.now(timezone.utc)
    await _handle_bee(frame, mock_conn)
    after = datetime.now(timezone.utc)

    insert = sql_calls(mock_conn.execute, 'INSERT INTO location_events')[0]
    args = insert.args
    # lon/lat order in the geometry: ST_MakePoint(x = longitude $7, y = latitude $6)
    assert 'ST_MakePoint($7, $6)' in args[0]
    # args[0] is the SQL text, so args[n] is $n
    assert args[1:5] == ('dev-uuid-1', 'user-uuid-1', 2, RECORDED)
    received_at = args[5]
    # server clock, never the device clock
    assert received_at.tzinfo is not None
    assert before <= received_at <= after
    assert abs((received_at - datetime.now(timezone.utc)).total_seconds()) < 5
    assert received_at != frame.recorded_at
    assert args[6:9] == (42.1438409, 24.7495615, '35TNH1234567890')
    assert args[9] == 321                # altitude_m
    assert args[10] == 7.5               # speed_knots
    assert args[11] == 211               # course_deg
    assert args[12] == 9                 # gnss_satellites
    assert args[13] == 3.9               # battery_voltage
    assert args[14] is False             # sos_active
    assert args[15] is True              # repeater_mode
    assert args[16] == 5                 # raw_flags
    assert args[17] is True              # gnss_valid

    p = notifies(mock_conn, 'location_update')[0]
    assert p == {
        'device_id': 'dev-uuid-1', 'user_id': 'user-uuid-1', 'full_name': 'Ivan Petrov', 'rank': 'Sgt',
        'photo_url': None, 'phone': '+359', 'mgrs': '35TNH1234567890',
        'latitude': 42.1438409, 'longitude': 24.7495615, 'altitude_m': 321, 'speed_knots': 7.5,
        'course_deg': 211, 'battery_voltage': 3.9, 'gnss_satellites': 9, 'gnss_valid': True,
        'sos_active': False, 'repeater_mode': True,
        'recorded_at': RECORDED.isoformat(), 'received_at': received_at.isoformat(),
        'groups': [{'id': 'g-uuid-1', 'name': 'Alpha', 'color': '#ff0', 'is_leader': True}],
    }
    assert p['received_at'] != p['recorded_at']


async def test_queries_filter_active_rows_and_order_newest_first(mock_conn):
    # a no-fix frame exercises the last-fix query; the SOS lookups need the previous-SOS query too
    last_fix = {'latitude': 42.1, 'longitude': 24.1, 'mgrs': '35TNH0000000000'}
    install(mock_conn, device=DEVICE, last_fix=last_fix, prev_sos=False, user=USER)

    await _handle_bee(bee_frame(gnss_valid=False), mock_conn)

    device_sql = sql_calls(mock_conn.fetchrow, 'FROM devices')[0].args[0]
    assert 'is_active = TRUE' in device_sql
    assert 'device_type = $2' in device_sql
    last_fix_sql = sql_calls(mock_conn.fetchrow, 'gnss_valid = TRUE')[0].args[0]
    assert 'ORDER BY received_at DESC LIMIT 1' in last_fix_sql
    prev_sos_sql = sql_calls(mock_conn.fetchval, 'SELECT sos_active')[0].args[0]
    assert 'ORDER BY received_at DESC LIMIT 1' in prev_sos_sql
    groups_sql = sql_calls(mock_conn.fetch, 'FROM user_groups')[0].args[0]
    assert 'g.is_active = TRUE' in groups_sql


async def test_userless_device_is_still_broadcast(mock_conn):
    install(mock_conn, device={'id': 'dev-uuid-1', 'user_id': None}, prev_sos=False, user=None)

    await _handle_bee(bee_frame(), mock_conn)

    inserts = sql_calls(mock_conn.execute, 'INSERT INTO location_events')
    assert len(inserts) == 1
    assert inserts[0].args[2] is None  # $2 user_id
    payloads = notifies(mock_conn, 'location_update')
    assert len(payloads) == 1
    assert payloads[0]['user_id'] is None
    assert payloads[0]['full_name'] is None
    assert payloads[0]['groups'] == []
