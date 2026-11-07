"""B72: /api/locations/live and the location_update push agree on sos_active.

Rule: an open alert (sos_alerts.resolved_at IS NULL) is SOS until the operator resolves it,
whatever the raw flag of the latest frame says.
"""
import pytest

pytestmark = [pytest.mark.Trait("Task", "B72")]


async def _device_with_frame(c, sn, raw_sos):
    dev = await c.fetchval('INSERT INTO devices (dev_sn) VALUES ($1) RETURNING id', sn)
    await c.execute(
        "INSERT INTO location_events (device_id, msg_id, mgrs, latitude, longitude, position, "
        "sos_active, received_at, recorded_at) "
        "VALUES ($1, 1, '35TLF1234512345', 42.5, 24.5, ST_SetSRID(ST_MakePoint(24.5, 42.5), 4326), "
        "$2, NOW(), NOW())", dev, raw_sos)
    return dev


async def _push_value(c, dev):
    # The exact query reader.py uses for the location_update payload.
    return await c.fetchval(
        'SELECT EXISTS(SELECT 1 FROM sos_alerts WHERE device_id = $1 AND resolved_at IS NULL)', dev)


@pytest.mark.Trait("Task", "B72")
@pytest.mark.db
@pytest.mark.asyncio
async def test_live_open_alert_is_sos_even_when_raw_flag_cleared(migrated_conn):
    from backend.routers import locations
    c = migrated_conn
    dev = await _device_with_frame(c, 7201, False)
    await c.execute('INSERT INTO sos_alerts (device_id, triggered_at) VALUES ($1, NOW())', dev)
    rows = await locations.live_positions(c, {'id': None})
    assert len(rows) == 1
    assert rows[0]['sos_active'] is True
    assert rows[0]['sos_active'] == await _push_value(c, dev)


@pytest.mark.Trait("Task", "B72")
@pytest.mark.db
@pytest.mark.asyncio
async def test_live_resolved_alert_is_not_sos_even_when_raw_flag_set(migrated_conn):
    from backend.routers import locations
    c = migrated_conn
    dev = await _device_with_frame(c, 7202, True)
    await c.execute('INSERT INTO sos_alerts (device_id, triggered_at, resolved_at) VALUES ($1, NOW(), NOW())', dev)
    rows = await locations.live_positions(c, {'id': None})
    assert rows[0]['sos_active'] is False
    assert rows[0]['sos_active'] == await _push_value(c, dev)
