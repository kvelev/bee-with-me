"""Devices against a real migrated schema: permanent delete and serial uniqueness."""
import asyncpg
import pytest
from fastapi import HTTPException

pytestmark = [pytest.mark.Trait("Task", "T112"), pytest.mark.db, pytest.mark.asyncio]

_INSERT_EVENT = (
    "INSERT INTO location_events (device_id, msg_id, mgrs, latitude, longitude, position, recorded_at) "
    "VALUES ($1, 1, '35TLF1234512345', 42.5, 24.5, ST_SetSRID(ST_MakePoint(24.5, 42.5), 4326), NOW())"
)


async def _admin(c):
    return await c.fetchval("INSERT INTO users (full_name, role) VALUES ('Admin', 'admin') RETURNING id")


async def _open_rescuer_alert(c, device_id):
    hotspot = await c.fetchval(
        "INSERT INTO fire_hotspots (source, effis_id, acquired_at, latitude, longitude) "
        "VALUES ('viirs', $1, NOW(), 42.5, 24.5) RETURNING id", str(device_id))
    return await c.fetchval(
        "INSERT INTO fire_alerts (hotspot_id, target_type, device_id, distance_m) "
        "VALUES ($1, 'rescuer', $2, 100) RETURNING id", hotspot, device_id)


async def test_permanent_delete_removes_events_and_resolves_fire_alerts(migrated_conn):
    from backend.routers import devices
    c = migrated_conn
    admin = await _admin(c)
    dev = await c.fetchval('INSERT INTO devices (dev_sn) VALUES (21) RETURNING id')
    await c.execute(_INSERT_EVENT, dev)
    await c.execute(_INSERT_EVENT, dev)
    await c.execute('INSERT INTO sos_alerts (device_id, triggered_at) VALUES ($1, NOW())', dev)
    await c.execute('INSERT INTO repeater_events (device_id, msg_id) VALUES ($1, 1)', dev)
    alert = await _open_rescuer_alert(c, dev)

    await devices.delete_device_permanent(dev, c, {'id': admin})

    assert await c.fetchval('SELECT COUNT(*) FROM devices WHERE id = $1', dev) == 0
    for table in ('location_events', 'sos_alerts', 'repeater_events'):
        assert await c.fetchval(f'SELECT COUNT(*) FROM {table} WHERE device_id = $1', dev) == 0
    row = await c.fetchrow('SELECT * FROM fire_alerts WHERE id = $1', alert)
    assert row['resolved_at'] is not None
    assert row['resolve_reason'] == 'disabled'
    assert row['resolved_by'] == admin
    assert row['device_id'] is None


async def test_permanent_delete_unknown_device_is_404_and_resolves_nothing(migrated_conn):
    import uuid
    from backend.routers import devices
    c = migrated_conn
    admin = await _admin(c)
    other = await c.fetchval('INSERT INTO devices (dev_sn) VALUES (22) RETURNING id')
    alert = await _open_rescuer_alert(c, other)

    with pytest.raises(HTTPException) as exc:
        await devices.delete_device_permanent(uuid.uuid4(), c, {'id': admin})

    assert exc.value.status_code == 404
    row = await c.fetchrow('SELECT resolved_at, resolve_reason FROM fire_alerts WHERE id = $1', alert)
    assert row['resolved_at'] is None
    assert row['resolve_reason'] is None
    assert await c.fetchval('SELECT COUNT(*) FROM devices WHERE id = $1', other) == 1


async def test_dev_sn_is_unique_per_type_only(migrated_conn):
    c = migrated_conn
    await c.execute("INSERT INTO devices (dev_sn, device_type) VALUES (10, 'bee')")
    await c.execute("INSERT INTO devices (dev_sn, device_type) VALUES (10, 'repeater')")
    with pytest.raises(asyncpg.UniqueViolationError):
        await c.execute("INSERT INTO devices (dev_sn, device_type) VALUES (10, 'bee')")
