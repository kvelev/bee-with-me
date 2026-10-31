"""Tracking and SOS against a real migrated schema."""
import pytest

from backend.config import settings

pytestmark = [pytest.mark.Trait("Task", "T111"), pytest.mark.db, pytest.mark.asyncio]

_INSERT_EVENT = (
    "INSERT INTO location_events (device_id, user_id, msg_id, mgrs, latitude, longitude, position, "
    "received_at, recorded_at, gnss_valid, sos_active) "
    "VALUES ($1, $2, 1, '35TLF1234512345', 42.5, 24.5, ST_SetSRID(ST_MakePoint(24.5, 42.5), 4326), "
    "NOW() - make_interval(mins => $3), NOW() - make_interval(mins => $3), $4, $5)"
)


# A fresh valid fix at a chosen latitude, received $3 minutes ago
_INSERT_AT = (
    "INSERT INTO location_events (device_id, user_id, msg_id, mgrs, latitude, longitude, position, "
    "received_at, recorded_at, gnss_valid, sos_active) "
    "VALUES ($1, $2, 1, '35TLF1234512345', $4, 24.5, ST_SetSRID(ST_MakePoint(24.5, $4), 4326), "
    "NOW() - make_interval(mins => $3), NOW() - make_interval(mins => $3), TRUE, FALSE)"
)

async def _user(c, name, active=True):
    return await c.fetchval(
        "INSERT INTO users (full_name, role, is_active) VALUES ($1, 'rescuer', $2) RETURNING id", name, active)


async def _device(c, sn, user_id=None):
    return await c.fetchval('INSERT INTO devices (dev_sn, user_id) VALUES ($1, $2) RETURNING id', sn, user_id)


async def test_live_hides_inactive_users_and_old_positions(migrated_conn):
    from backend.routers import locations
    c = migrated_conn
    ua, ub = await _user(c, 'A'), await _user(c, 'B', active=False)
    d1, d2, d3 = await _device(c, 1, ua), await _device(c, 2, ub), await _device(c, 3)
    await c.execute(_INSERT_EVENT, d1, ua, 0, True, False)
    await c.execute(_INSERT_EVENT, d2, ub, 0, True, False)
    old_minutes = (settings.live_position_max_age_hours + 1) * 60
    await c.execute(_INSERT_EVENT, d3, None, old_minutes, True, False)
    rows = await locations.live_positions(c, {'id': ua})
    assert [r['device_id'] for r in rows] == [d1]


async def test_live_newest_received_position_wins(migrated_conn):
    from backend.routers import locations
    c = migrated_conn
    u = await _user(c, 'A')
    d = await _device(c, 1, u)
    # the newer position is inserted first, so "last inserted" and "newest received_at" disagree
    await c.execute(_INSERT_AT, d, u, 1, 43.25)
    await c.execute(_INSERT_AT, d, u, 10, 42.75)

    rows = await locations.live_positions(c, {'id': u})

    assert [(r['device_id'], r['latitude']) for r in rows] == [(d, 43.25)]


async def test_live_excludes_inactive_devices_and_keeps_userless_ones(migrated_conn):
    from backend.routers import locations
    c = migrated_conn
    u = await _user(c, 'A')
    retired = await _device(c, 1, u)
    await c.execute('UPDATE devices SET is_active = FALSE WHERE id = $1', retired)
    spare = await _device(c, 2)   # active, nobody assigned
    await c.execute(_INSERT_EVENT, retired, u, 0, True, False)
    await c.execute(_INSERT_EVENT, spare, None, 0, True, False)

    rows = await locations.live_positions(c, {'id': u})

    assert [r['device_id'] for r in rows] == [spare]
    assert rows[0]['user_id'] is None


async def test_live_sos_active_requires_an_open_alert(migrated_conn):
    from backend.routers import locations
    c = migrated_conn
    u = await _user(c, 'A')
    d = await _device(c, 1, u)
    await c.execute(_INSERT_EVENT, d, u, 0, True, True)
    rows = await locations.live_positions(c, {'id': u})
    assert [r['sos_active'] for r in rows] == [False]
    await c.execute('INSERT INTO sos_alerts (device_id, user_id, triggered_at) VALUES ($1, $2, NOW())', d, u)
    rows = await locations.live_positions(c, {'id': u})
    assert [r['sos_active'] for r in rows] == [True]


async def test_trail_cuts_at_the_current_assignment(migrated_conn):
    from backend.routers import devices, locations
    c = migrated_conn
    admin = await c.fetchval("INSERT INTO users (full_name, role) VALUES ('Admin', 'admin') RETURNING id")
    previous, current = await _user(c, 'Previous'), await _user(c, 'Current')
    d = await _device(c, 1, previous)
    await c.execute(_INSERT_EVENT, d, previous, 5, True, False)   # inside the window, before the handover
    await devices.assign_device(d, devices.AssignRequest(user_id=current), c, {'id': admin})
    await c.execute(_INSERT_EVENT, d, current, 0, True, False)    # after the handover

    assigned_at = await c.fetchval('SELECT assigned_at FROM devices WHERE id = $1', d)
    after = await c.fetchval(
        'SELECT received_at FROM location_events WHERE device_id = $1 AND user_id = $2', d, current)
    trail = await locations.location_trail(c, {'id': admin}, minutes=30)

    assert assigned_at is not None
    assert list(trail.keys()) == [str(d)]
    assert [p['received_at'] for p in trail[str(d)]] == [after.isoformat()]
    assert after > assigned_at


async def test_trail_excludes_points_older_than_the_window(migrated_conn):
    from backend.routers import locations
    c = migrated_conn
    u = await _user(c, 'A')
    d = await _device(c, 1, u)   # never reassigned: assigned_at is NULL, only the window cuts
    await c.execute(_INSERT_EVENT, d, u, 40, True, False)
    await c.execute(_INSERT_EVENT, d, u, 5, True, False)
    recent = await c.fetchval(
        'SELECT MAX(received_at) FROM location_events WHERE device_id = $1', d)

    trail = await locations.location_trail(c, {'id': u}, minutes=30)

    assert await c.fetchval('SELECT assigned_at FROM devices WHERE id = $1', d) is None
    assert [p['received_at'] for p in trail[str(d)]] == [recent.isoformat()]


async def test_trail_skips_positions_without_fix(migrated_conn):
    from backend.routers import locations
    c = migrated_conn
    u = await _user(c, 'A')
    d = await _device(c, 1, u)
    await c.execute(_INSERT_EVENT, d, u, 5, False, False)
    await c.execute(_INSERT_EVENT, d, u, 4, True, False)
    trail = await locations.location_trail(c, {'id': u}, minutes=30)
    assert len(trail[str(d)]) == 1


async def test_resolve_sos_twice_keeps_the_first_resolver(migrated_conn):
    from backend.routers import locations
    c = migrated_conn
    u1, u2 = await _user(c, 'One'), await _user(c, 'Two')
    d = await _device(c, 1, u1)
    alert = await c.fetchval(
        'INSERT INTO sos_alerts (device_id, user_id, triggered_at) VALUES ($1, $2, NOW()) RETURNING id', d, u1)
    await locations.resolve_sos(alert, None, c, {'id': u1})
    first = await c.fetchrow('SELECT resolved_by, resolved_at FROM sos_alerts WHERE id = $1', alert)
    await locations.resolve_sos(alert, None, c, {'id': u2})
    second = await c.fetchrow('SELECT resolved_by, resolved_at FROM sos_alerts WHERE id = $1', alert)
    assert first['resolved_by'] == u1
    assert second['resolved_by'] == u1
    assert second['resolved_at'] == first['resolved_at']


@pytest.mark.xfail(strict=True, raises=AssertionError, reason='B72: /live and the push disagree on sos_active')
async def test_live_sos_active_follows_the_open_alert_not_the_raw_flag(migrated_conn):
    # The push (reader.py) broadcasts "an alert is open"; /live computes raw flag AND open alert.
    # Raw flag False with an unresolved alert: the push says True, /live says False.
    from backend.routers import locations
    c = migrated_conn
    u = await _user(c, 'A')
    d = await _device(c, 1, u)
    await c.execute('INSERT INTO sos_alerts (device_id, user_id, triggered_at) VALUES ($1, $2, NOW())', d, u)
    await c.execute(_INSERT_EVENT, d, u, 0, True, False)

    rows = await locations.live_positions(c, {'id': u})

    assert [r['sos_active'] for r in rows] == [True]
