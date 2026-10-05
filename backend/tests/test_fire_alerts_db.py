import pytest

from backend.fire import repository

pytestmark = [pytest.mark.Trait("Task", "T16"), pytest.mark.db, pytest.mark.asyncio]


async def _seed(conn):
    hotspot = await conn.fetchval(
        "INSERT INTO fire_hotspots (source, effis_id, acquired_at, latitude, longitude) "
        "VALUES ('viirs', 'h1', NOW(), 42.5, 24.5) RETURNING id")
    device = await conn.fetchval('INSERT INTO devices (dev_sn) VALUES (7) RETURNING id')
    alert = await conn.fetchval(
        "INSERT INTO fire_alerts (hotspot_id, target_type, device_id, distance_m) "
        "VALUES ($1, 'rescuer', $2, 900) RETURNING id::text", hotspot, device)
    admin = await conn.fetchval("INSERT INTO users (full_name, role) VALUES ('Admin', 'admin') RETURNING id")
    return hotspot, device, alert, admin


async def test_acknowledge_once_then_unchanged(migrated_conn):
    _, _, alert, admin = await _seed(migrated_conn)
    out, changed = await repository.acknowledge_alert(migrated_conn, alert, admin)
    assert changed and out.acknowledged_at is not None
    again, changed = await repository.acknowledge_alert(migrated_conn, alert, admin)
    assert not changed and again.acknowledged_at == out.acknowledged_at
    missing, changed = await repository.acknowledge_alert(migrated_conn, '00000000-0000-7000-8000-000000000000', admin)
    assert missing is None and not changed


async def test_list_alerts_open_and_all(migrated_conn):
    _, _, alert, _ = await _seed(migrated_conn)
    assert [str(a.id) for a in await repository.list_alerts(migrated_conn, 'open', 50, 0)] == [alert]
    await repository.resolve_alert(migrated_conn, alert, 'aged_out')
    assert await repository.list_alerts(migrated_conn, 'open', 50, 0) == []
    [resolved] = await repository.list_alerts(migrated_conn, 'all', 50, 0)
    assert resolved.resolve_reason == 'aged_out'


async def test_prune_keeps_hotspots_that_alerts_point_at(migrated_conn):
    await _seed(migrated_conn)
    await migrated_conn.execute("UPDATE fire_hotspots SET last_seen_at = NOW() - INTERVAL '30 days'")
    assert (await repository.prune_fire_data(migrated_conn))['fire_hotspots'] == 0


async def test_permanent_device_delete_resolves_open_alerts(migrated_conn):
    from backend.routers import devices
    _, device, alert, admin = await _seed(migrated_conn)
    # Call the endpoint function directly on the real connection (TestClient runs its own event loop,
    # which can't share this asyncpg connection). The deleting user must exist: B42 records it in resolved_by.
    await devices.delete_device_permanent(device, migrated_conn, {'id': admin})
    row = await migrated_conn.fetchrow(
        'SELECT resolve_reason::text, device_id FROM fire_alerts WHERE id = $1::uuid', alert)
    assert row['resolve_reason'] == 'disabled' and row['device_id'] is None


@pytest.mark.Trait("Bug", "B42")
async def test_permanent_device_delete_records_who_resolved(migrated_conn):
    from backend.routers import devices
    _, device, alert, admin = await _seed(migrated_conn)
    await devices.delete_device_permanent(device, migrated_conn, {'id': admin})
    row = await migrated_conn.fetchrow(
        'SELECT resolve_reason::text, resolved_by FROM fire_alerts WHERE id = $1::uuid', alert)
    assert row['resolve_reason'] == 'disabled' and row['resolved_by'] == admin


@pytest.mark.Trait("Bug", "B44")
async def test_acknowledge_all_with_ids_only_acknowledges_those(migrated_conn):
    import uuid
    hotspot, device, alert, admin = await _seed(migrated_conn)
    other = await migrated_conn.fetchval(
        "INSERT INTO fire_alerts (hotspot_id, target_type, distance_m) VALUES ($1, 'hq', 500) RETURNING id::text",
        hotspot)
    assert await repository.acknowledge_all(migrated_conn, admin, [uuid.UUID(alert)]) == [alert]
    assert (await repository.get_alert_out(migrated_conn, other)).acknowledged_at is None
    assert await repository.acknowledge_all(migrated_conn, admin, []) == []
    assert await repository.acknowledge_all(migrated_conn, admin) == [other]


@pytest.mark.Trait("Bug", "B44")
async def test_count_alerts_ignores_paging(migrated_conn):
    hotspot, _, alert, _ = await _seed(migrated_conn)
    await migrated_conn.execute(
        "INSERT INTO fire_alerts (hotspot_id, target_type, distance_m) VALUES ($1, 'hq', 500)", hotspot)
    assert await repository.count_alerts(migrated_conn, 'open') == 2
    await repository.resolve_alert(migrated_conn, alert, 'aged_out')
    assert await repository.count_alerts(migrated_conn, 'open') == 1
    assert await repository.count_alerts(migrated_conn, 'all') == 2


@pytest.mark.Trait("Bug", "B44")
async def test_open_alert_shows_the_current_device_holder(migrated_conn):
    _, device, alert, admin = await _seed(migrated_conn)
    old = await migrated_conn.fetchval("INSERT INTO users (full_name, role) VALUES ('Old Holder', 'rescuer') RETURNING id")
    new = await migrated_conn.fetchval("INSERT INTO users (full_name, role) VALUES ('New Holder', 'rescuer') RETURNING id")
    await migrated_conn.execute('UPDATE fire_alerts SET user_id = $1 WHERE id = $2::uuid', old, alert)
    await migrated_conn.execute('UPDATE devices SET user_id = $1 WHERE id = $2', new, device)
    out = await repository.get_alert_out(migrated_conn, alert)
    assert out.full_name == 'New Holder' and out.user_id == new
    # a device without a holder falls back to the alert's own user
    await migrated_conn.execute('UPDATE devices SET user_id = NULL WHERE id = $1', device)
    assert (await repository.get_alert_out(migrated_conn, alert)).full_name == 'Old Holder'
    # a resolved alert keeps the person it was raised for
    await migrated_conn.execute('UPDATE devices SET user_id = $1 WHERE id = $2', new, device)
    await repository.resolve_alert(migrated_conn, alert, 'aged_out')
    assert (await repository.get_alert_out(migrated_conn, alert)).full_name == 'Old Holder'


@pytest.mark.Trait("Bug", "B47")
async def test_resolve_disabled_alerts_only_for_inactive_device_or_holder(migrated_conn):
    _, device, alert, admin = await _seed(migrated_conn)
    # an active, merely silent rescuer keeps its alert (B40)
    assert await repository.resolve_disabled_alerts(migrated_conn) == []
    await migrated_conn.execute('UPDATE devices SET is_active = FALSE WHERE id = $1', device)
    assert await repository.resolve_disabled_alerts(migrated_conn, device_id=None) == [alert]
    row = await migrated_conn.fetchrow(
        'SELECT resolve_reason::text, resolved_by FROM fire_alerts WHERE id = $1::uuid', alert)
    assert row['resolve_reason'] == 'disabled' and row['resolved_by'] is None
    assert await repository.resolve_disabled_alerts(migrated_conn) == []   # already resolved: idempotent


@pytest.mark.Trait("Bug", "B47")
async def test_resolve_disabled_alerts_scoped_to_a_deactivated_user_records_the_admin(migrated_conn):
    _, device, alert, admin = await _seed(migrated_conn)
    holder = await migrated_conn.fetchval("INSERT INTO users (full_name, role) VALUES ('Holder', 'rescuer') RETURNING id")
    await migrated_conn.execute('UPDATE devices SET user_id = $1 WHERE id = $2', holder, device)
    other = await migrated_conn.fetchval("INSERT INTO users (full_name, role) VALUES ('Other', 'rescuer') RETURNING id")
    await migrated_conn.execute('UPDATE users SET is_active = FALSE WHERE id IN ($1, $2)', holder, other)
    assert await repository.resolve_disabled_alerts(migrated_conn, admin, user_id=other) == []
    assert await repository.resolve_disabled_alerts(migrated_conn, admin, user_id=holder) == [alert]
    row = await migrated_conn.fetchrow('SELECT resolved_by FROM fire_alerts WHERE id = $1::uuid', alert)
    assert row['resolved_by'] == admin


@pytest.mark.Trait("Bug", "B46")
async def test_open_alerts_list_puts_unacknowledged_before_newer_acknowledged(migrated_conn):
    hotspot, device, older, admin = await _seed(migrated_conn)
    device2 = await migrated_conn.fetchval('INSERT INTO devices (dev_sn) VALUES (8) RETURNING id')
    newer = await migrated_conn.fetchval(
        "INSERT INTO fire_alerts (hotspot_id, target_type, device_id, distance_m, triggered_at) "
        "VALUES ($1, 'rescuer', $2, 500, NOW() + INTERVAL '1 minute') RETURNING id::text", hotspot, device2)
    await repository.acknowledge_alert(migrated_conn, newer, admin)
    assert [str(a.id) for a in await repository.list_alerts(migrated_conn, 'open', 50, 0)] == [older, newer]
    assert [str(a.id) for a in await repository.list_alerts(migrated_conn, 'all', 50, 0)] == [newer, older]


async def test_clearing_hq_resolves_an_acknowledged_hq_alert_so_a_new_hq_alarms_again(migrated_conn):
    hotspot, _, rescuer_alert, admin = await _seed(migrated_conn)
    hq_alert = await migrated_conn.fetchval(
        "INSERT INTO fire_alerts (hotspot_id, target_type, distance_m) VALUES ($1, 'hq', 4000) RETURNING id::text",
        hotspot)
    await repository.acknowledge_alert(migrated_conn, hq_alert, admin)
    assert await repository.resolve_hq_alerts(migrated_conn, admin) == [hq_alert]
    row = await migrated_conn.fetchrow(
        'SELECT resolve_reason::text, resolved_by FROM fire_alerts WHERE id = $1::uuid', hq_alert)
    assert row['resolve_reason'] == 'disabled' and row['resolved_by'] == admin
    # rescuer alerts are not HQ alerts
    assert await migrated_conn.fetchval(
        'SELECT resolved_at IS NULL FROM fire_alerts WHERE id = $1::uuid', rescuer_alert)
    # the hotspot is free again: an HQ set next to the same fire gets a new, unacknowledged alert
    await migrated_conn.execute(
        "INSERT INTO fire_alerts (hotspot_id, target_type, distance_m) VALUES ($1, 'hq', 4000)", hotspot)
    assert await repository.resolve_hq_alerts(migrated_conn, None) != []
    assert await repository.resolve_hq_alerts(migrated_conn, None) == []   # idempotent
