"""T542: the reader's handlers hand their SQL to `tracking.api` and `sos.api` and change nothing else.

`EXPECTED` was recorded by running `_handle_bee` and `_handle_repeater` on the UNCHANGED `reader.py` (develop at
43faaf8) against the routed fake connection of `gateway_fakes.py`, with the clock frozen. Each entry is the ordered list
of (method, sql text with whitespace collapsed, args) the handler issued on the connection.
"""
import datetime
from pathlib import Path

import pytest

from backend.hardware_reader import hid_reader, reader
from backend.tests.modules.gateway.delegates_helper import CASES, run_case

EXPECTED = {'fix': [('fetchrow',
          'SELECT id, user_id FROM devices WHERE dev_sn = $1 AND device_type = $2 AND is_active = TRUE',
          (1235, 'bee')),
         ('fetchval',
          'SELECT sos_active FROM location_events WHERE device_id = $1 ORDER BY received_at DESC LIMIT 1',
          ('dev-uuid-1',)),
         ('execute',
          'INSERT INTO location_events ( device_id, user_id, msg_id, recorded_at, received_at, position, '
          'latitude, longitude, mgrs, altitude_m, speed_knots, course_deg, gnss_satellites, battery_voltage, '
          'sos_active, repeater_mode, raw_flags, gnss_valid ) VALUES ( $1, $2, $3, $4, $5, '
          'ST_SetSRID(ST_MakePoint($7, $6), 4326), $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17 )',
          ('dev-uuid-1',
           'user-uuid-1',
           2,
           datetime.datetime(2024, 12, 8, 20, 50, 5, tzinfo=datetime.timezone.utc),
           datetime.datetime(2024, 12, 8, 21, 0, tzinfo=datetime.timezone.utc),
           42.1438409,
           24.7495615,
           '35TNH1234567890',
           200,
           5.0,
           137,
           12,
           3.7,
           False,
           False,
           0,
           True)),
         ('fetchval',
          'SELECT EXISTS(SELECT 1 FROM sos_alerts WHERE device_id = $1 AND resolved_at IS NULL)',
          ('dev-uuid-1',)),
         ('fetchrow',
          'SELECT full_name, rank, photo_url, phone, is_active FROM users WHERE id = $1',
          ('user-uuid-1',)),
         ('fetch',
          'SELECT g.id, g.name, g.color, ug.is_leader FROM user_groups ug JOIN groups g ON g.id = '
          'ug.group_id WHERE ug.user_id = $1 AND g.is_active = TRUE',
          ('user-uuid-1',)),
         ('execute',
          "SELECT pg_notify('location_update', $1)",
          ('{"device_id": "dev-uuid-1", "user_id": "user-uuid-1", "full_name": "Ivan Petrov", "rank": "Sgt", '
           '"photo_url": null, "phone": "+359", "mgrs": "35TNH1234567890", "latitude": 42.1438409, '
           '"longitude": 24.7495615, "altitude_m": 200, "speed_knots": 5.0, "course_deg": 137, '
           '"battery_voltage": 3.7, "gnss_satellites": 12, "gnss_valid": true, "sos_active": false, '
           '"repeater_mode": false, "recorded_at": "2024-12-08T20:50:05+00:00", "received_at": '
           '"2024-12-08T21:00:00+00:00", "groups": []}',))],
 'no_fix_with_previous_fix': [('fetchrow',
                               'SELECT id, user_id FROM devices WHERE dev_sn = $1 AND device_type = $2 AND '
                               'is_active = TRUE',
                               (1235, 'bee')),
                              ('fetchrow',
                               'SELECT latitude, longitude, mgrs FROM location_events WHERE device_id = $1 '
                               'AND gnss_valid = TRUE ORDER BY received_at DESC LIMIT 1',
                               ('dev-uuid-1',)),
                              ('fetchval',
                               'SELECT sos_active FROM location_events WHERE device_id = $1 ORDER BY '
                               'received_at DESC LIMIT 1',
                               ('dev-uuid-1',)),
                              ('execute',
                               'INSERT INTO location_events ( device_id, user_id, msg_id, recorded_at, '
                               'received_at, position, latitude, longitude, mgrs, altitude_m, speed_knots, '
                               'course_deg, gnss_satellites, battery_voltage, sos_active, repeater_mode, '
                               'raw_flags, gnss_valid ) VALUES ( $1, $2, $3, $4, $5, '
                               'ST_SetSRID(ST_MakePoint($7, $6), 4326), $6, $7, $8, $9, $10, $11, $12, $13, '
                               '$14, $15, $16, $17 )',
                               ('dev-uuid-1',
                                'user-uuid-1',
                                2,
                                datetime.datetime(2024, 12, 8, 20, 50, 5, tzinfo=datetime.timezone.utc),
                                datetime.datetime(2024, 12, 8, 21, 0, tzinfo=datetime.timezone.utc),
                                42.1,
                                24.1,
                                '35TNH0000000000',
                                200,
                                5.0,
                                137,
                                12,
                                3.7,
                                False,
                                False,
                                0,
                                False)),
                              ('fetchval',
                               'SELECT EXISTS(SELECT 1 FROM sos_alerts WHERE device_id = $1 AND resolved_at '
                               'IS NULL)',
                               ('dev-uuid-1',)),
                              ('fetchrow',
                               'SELECT full_name, rank, photo_url, phone, is_active FROM users WHERE id = $1',
                               ('user-uuid-1',)),
                              ('fetch',
                               'SELECT g.id, g.name, g.color, ug.is_leader FROM user_groups ug JOIN groups g '
                               'ON g.id = ug.group_id WHERE ug.user_id = $1 AND g.is_active = TRUE',
                               ('user-uuid-1',)),
                              ('execute',
                               "SELECT pg_notify('location_update', $1)",
                               ('{"device_id": "dev-uuid-1", "user_id": "user-uuid-1", "full_name": "Ivan '
                                'Petrov", "rank": "Sgt", "photo_url": null, "phone": "+359", "mgrs": '
                                '"35TNH0000000000", "latitude": 42.1, "longitude": 24.1, "altitude_m": 200, '
                                '"speed_knots": 5.0, "course_deg": 137, "battery_voltage": 3.7, '
                                '"gnss_satellites": 12, "gnss_valid": false, "sos_active": false, '
                                '"repeater_mode": false, "recorded_at": "2024-12-08T20:50:05+00:00", '
                                '"received_at": "2024-12-08T21:00:00+00:00", "groups": []}',))],
 'no_fix_without_previous_fix': [('fetchrow',
                                  'SELECT id, user_id FROM devices WHERE dev_sn = $1 AND device_type = $2 '
                                  'AND is_active = TRUE',
                                  (1235, 'bee')),
                                 ('fetchrow',
                                  'SELECT latitude, longitude, mgrs FROM location_events WHERE device_id = '
                                  '$1 AND gnss_valid = TRUE ORDER BY received_at DESC LIMIT 1',
                                  ('dev-uuid-1',))],
 'rising_sos': [('fetchrow',
                 'SELECT id, user_id FROM devices WHERE dev_sn = $1 AND device_type = $2 AND is_active = '
                 'TRUE',
                 (1235, 'bee')),
                ('fetchval',
                 'SELECT sos_active FROM location_events WHERE device_id = $1 ORDER BY received_at DESC '
                 'LIMIT 1',
                 ('dev-uuid-1',)),
                ('execute',
                 'INSERT INTO location_events ( device_id, user_id, msg_id, recorded_at, received_at, '
                 'position, latitude, longitude, mgrs, altitude_m, speed_knots, course_deg, gnss_satellites, '
                 'battery_voltage, sos_active, repeater_mode, raw_flags, gnss_valid ) VALUES ( $1, $2, $3, '
                 '$4, $5, ST_SetSRID(ST_MakePoint($7, $6), 4326), $6, $7, $8, $9, $10, $11, $12, $13, $14, '
                 '$15, $16, $17 )',
                 ('dev-uuid-1',
                  'user-uuid-1',
                  2,
                  datetime.datetime(2024, 12, 8, 20, 50, 5, tzinfo=datetime.timezone.utc),
                  datetime.datetime(2024, 12, 8, 21, 0, tzinfo=datetime.timezone.utc),
                  42.1438409,
                  24.7495615,
                  '35TNH1234567890',
                  200,
                  5.0,
                  137,
                  12,
                  3.7,
                  True,
                  False,
                  0,
                  True)),
                ('fetchrow',
                 'SELECT id FROM sos_alerts WHERE device_id = $1 AND resolved_at IS NULL',
                 ('dev-uuid-1',)),
                ('fetchrow',
                 'INSERT INTO sos_alerts (device_id, user_id, triggered_at) VALUES ($1, $2, $3) RETURNING '
                 'id, triggered_at',
                 ('dev-uuid-1',
                  'user-uuid-1',
                  datetime.datetime(2024, 12, 8, 20, 50, 5, tzinfo=datetime.timezone.utc))),
                ('fetchrow', 'SELECT full_name, rank FROM users WHERE id = $1', ('user-uuid-1',)),
                ('execute',
                 "SELECT pg_notify('sos_alert', $1)",
                 ('{"id": "alert-uuid-1", "device_id": "dev-uuid-1", "user_id": "user-uuid-1", "dev_sn": '
                  '1235, "full_name": "Ivan Petrov", "rank": "Sgt", "triggered_at": '
                  '"2024-12-08T20:50:05+00:00"}',)),
                ('fetchval',
                 'SELECT EXISTS(SELECT 1 FROM sos_alerts WHERE device_id = $1 AND resolved_at IS NULL)',
                 ('dev-uuid-1',)),
                ('fetchrow',
                 'SELECT full_name, rank, photo_url, phone, is_active FROM users WHERE id = $1',
                 ('user-uuid-1',)),
                ('fetch',
                 'SELECT g.id, g.name, g.color, ug.is_leader FROM user_groups ug JOIN groups g ON g.id = '
                 'ug.group_id WHERE ug.user_id = $1 AND g.is_active = TRUE',
                 ('user-uuid-1',)),
                ('execute',
                 "SELECT pg_notify('location_update', $1)",
                 ('{"device_id": "dev-uuid-1", "user_id": "user-uuid-1", "full_name": "Ivan Petrov", "rank": '
                  '"Sgt", "photo_url": null, "phone": "+359", "mgrs": "35TNH1234567890", "latitude": '
                  '42.1438409, "longitude": 24.7495615, "altitude_m": 200, "speed_knots": 5.0, "course_deg": '
                  '137, "battery_voltage": 3.7, "gnss_satellites": 12, "gnss_valid": true, "sos_active": '
                  'true, "repeater_mode": false, "recorded_at": "2024-12-08T20:50:05+00:00", "received_at": '
                  '"2024-12-08T21:00:00+00:00", "groups": []}',))],
 'inactive_person': [('fetchrow',
                      'SELECT id, user_id FROM devices WHERE dev_sn = $1 AND device_type = $2 AND is_active '
                      '= TRUE',
                      (1235, 'bee')),
                     ('fetchval',
                      'SELECT sos_active FROM location_events WHERE device_id = $1 ORDER BY received_at DESC '
                      'LIMIT 1',
                      ('dev-uuid-1',)),
                     ('execute',
                      'INSERT INTO location_events ( device_id, user_id, msg_id, recorded_at, received_at, '
                      'position, latitude, longitude, mgrs, altitude_m, speed_knots, course_deg, '
                      'gnss_satellites, battery_voltage, sos_active, repeater_mode, raw_flags, gnss_valid ) '
                      'VALUES ( $1, $2, $3, $4, $5, ST_SetSRID(ST_MakePoint($7, $6), 4326), $6, $7, $8, $9, '
                      '$10, $11, $12, $13, $14, $15, $16, $17 )',
                      ('dev-uuid-1',
                       'user-uuid-1',
                       2,
                       datetime.datetime(2024, 12, 8, 20, 50, 5, tzinfo=datetime.timezone.utc),
                       datetime.datetime(2024, 12, 8, 21, 0, tzinfo=datetime.timezone.utc),
                       42.1438409,
                       24.7495615,
                       '35TNH1234567890',
                       200,
                       5.0,
                       137,
                       12,
                       3.7,
                       False,
                       False,
                       0,
                       True)),
                     ('fetchval',
                      'SELECT EXISTS(SELECT 1 FROM sos_alerts WHERE device_id = $1 AND resolved_at IS NULL)',
                      ('dev-uuid-1',)),
                     ('fetchrow',
                      'SELECT full_name, rank, photo_url, phone, is_active FROM users WHERE id = $1',
                      ('user-uuid-1',))],
 'repeater_heartbeat': [('fetchrow',
                         'SELECT id, user_id FROM devices WHERE dev_sn = $1 AND device_type = $2 AND '
                         'is_active = TRUE',
                         (1256, 'repeater')),
                        ('execute',
                         'INSERT INTO repeater_events (device_id, msg_id, battery_voltage) VALUES ($1, $2, '
                         '$3)',
                         ('rep-uuid-1', 100, 3.4))]}


@pytest.mark.Trait("Task", "T542")
@pytest.mark.parametrize('name', list(EXPECTED))
@pytest.mark.asyncio
async def test_the_handlers_run_the_same_statements_in_the_same_order(name, monkeypatch):
    assert set(EXPECTED) == set(CASES)
    assert await run_case(name, monkeypatch) == EXPECTED[name]


@pytest.mark.Trait("Task", "T542")
def test_reader_holds_no_sql_for_positions_or_alerts():
    text = Path(reader.__file__).read_text(encoding='utf-8')
    # code only: after the module docstring, before the trailing string that holds the old serial run()
    live = text.split('from __future__ import annotations', 1)[1].split('"""async def run()', 1)[0]
    for needle in ('INSERT INTO', 'location_events', 'sos_alerts', 'repeater_events', 'pg_notify'):
        assert needle not in live, needle


@pytest.mark.Trait("Task", "T542")
def test_hid_reader_still_binds_the_reader_handlers():
    assert hid_reader._handle_bee is reader._handle_bee
    assert hid_reader._handle_repeater is reader._handle_repeater
    assert hid_reader._connect_kwargs is reader._connect_kwargs
