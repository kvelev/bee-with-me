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
    from backend.routers import locations
    c = migrated_conn
    u = await _user(c, 'A')
    d = await _device(c, 1, u)
    await c.execute("UPDATE devices SET assigned_at = NOW() - interval '10 minutes' WHERE id = $1", d)
    await c.execute(_INSERT_EVENT, d, u, 20, True, False)
    await c.execute(_INSERT_EVENT, d, u, 5, True, False)
    trail = await locations.location_trail(c, {'id': u}, minutes=30)
    assert list(trail.keys()) == [str(d)]
    assert len(trail[str(d)]) == 1


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
