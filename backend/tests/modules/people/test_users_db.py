"""Deleting a person against a real migrated schema."""
import pytest

pytestmark = [pytest.mark.Trait("Task", "T113"), pytest.mark.db, pytest.mark.asyncio]


async def test_delete_user_cascade(migrated_conn):
    from backend.routers import users
    c = migrated_conn
    u = await c.fetchval("INSERT INTO users (full_name, role) VALUES ('U', 'rescuer') RETURNING id")
    g = await c.fetchval("INSERT INTO groups (name) VALUES ('G') RETURNING id")
    await c.execute('INSERT INTO user_groups (user_id, group_id) VALUES ($1, $2)', u, g)
    d = await c.fetchval('INSERT INTO devices (dev_sn, user_id) VALUES (1, $1) RETURNING id', u)
    await c.execute(
        "INSERT INTO location_events (device_id, user_id, msg_id, mgrs, latitude, longitude, position, "
        "received_at, recorded_at, gnss_valid, sos_active) "
        "VALUES ($1, $2, 1, '35TLF1234512345', 42.5, 24.5, ST_SetSRID(ST_MakePoint(24.5, 42.5), 4326), "
        "NOW(), NOW(), TRUE, FALSE)", d, u)
    await c.execute(
        'INSERT INTO sos_alerts (device_id, user_id, triggered_at, resolved_by, resolved_at) '
        'VALUES ($1, $2, NOW(), $2, NOW())', d, u)

    await users.delete_user(u, c, {'id': u})

    assert await c.fetchval('SELECT COUNT(*) FROM users WHERE id = $1', u) == 0
    assert await c.fetchval('SELECT user_id FROM location_events WHERE device_id = $1', d) is None
    sos = await c.fetchrow('SELECT user_id, resolved_by FROM sos_alerts WHERE device_id = $1', d)
    assert (sos['user_id'], sos['resolved_by']) == (None, None)
    assert await c.fetchval('SELECT COUNT(*) FROM user_groups WHERE group_id = $1', g) == 0
    assert await c.fetchval('SELECT COUNT(*) FROM devices WHERE id = $1 AND user_id IS NULL', d) == 1
