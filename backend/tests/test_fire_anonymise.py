"""B48: resolved fire alerts lose their named trace after the location retention (DP-03)."""

import asyncio

import pytest

from backend.fire import repository

DAYS = 90


async def _no_hotspots(_conn, _days):
    return 0


async def _seed_alert(conn, hotspot, device, user, *, resolved_days_ago):
    """One rescuer alert naming user/device/ack/resolve; resolved_days_ago=None leaves it open."""
    return await conn.fetchval(
        "INSERT INTO fire_alerts (hotspot_id, target_type, device_id, user_id, distance_m, acknowledged_at,"
        " acknowledged_by, resolved_at, resolved_by, resolve_reason)"
        " VALUES ($1, 'rescuer', $2, $3, 700, NOW(), $3,"
        " CASE WHEN $4::int IS NULL THEN NULL ELSE NOW() - ($4::int || ' days')::interval END, $3,"
        " CASE WHEN $4::int IS NULL THEN NULL ELSE 'dismissed'::fire_alert_resolve_reason END)"
        " RETURNING id", hotspot, device, user, resolved_days_ago)


async def _world(conn):
    hotspot = await conn.fetchval(
        "INSERT INTO fire_hotspots (source, effis_id, acquired_at, latitude, longitude)"
        " VALUES ('viirs', 'h1', NOW(), 42.5, 24.5) RETURNING id")
    user = await conn.fetchval("INSERT INTO users (full_name, role) VALUES ('Ivan', 'rescuer') RETURNING id")
    devices = [await conn.fetchval('INSERT INTO devices (dev_sn) VALUES ($1) RETURNING id', sn) for sn in (1, 2, 3)]
    return hotspot, user, devices


@pytest.mark.Trait("Bug", "B48")
@pytest.mark.db
@pytest.mark.asyncio
async def test_old_resolved_alert_is_anonymised_and_others_untouched(migrated_conn):
    hotspot, user, (d1, d2, d3) = await _world(migrated_conn)
    old = await _seed_alert(migrated_conn, hotspot, d1, user, resolved_days_ago=DAYS + 5)
    fresh = await _seed_alert(migrated_conn, hotspot, d2, user, resolved_days_ago=DAYS - 5)
    open_ = await _seed_alert(migrated_conn, hotspot, d3, user, resolved_days_ago=None)

    count = await repository.anonymise_resolved_alerts(migrated_conn, DAYS)
    assert count == 1

    row = await migrated_conn.fetchrow('SELECT * FROM fire_alerts WHERE id = $1', old)
    assert row['user_id'] is None and row['device_id'] is None
    assert row['acknowledged_by'] is None and row['resolved_by'] is None
    assert row['distance_m'] == 700 and row['hotspot_id'] == hotspot and row['target_type'] == 'rescuer'
    assert row['resolve_reason'] == 'dismissed' and row['resolved_at'] is not None
    assert row['acknowledged_at'] is not None and row['triggered_at'] is not None
    for alert_id, device in ((fresh, d2), (open_, d3)):
        r = await migrated_conn.fetchrow('SELECT * FROM fire_alerts WHERE id = $1', alert_id)
        assert r['user_id'] == user and r['device_id'] == device
        assert r['acknowledged_by'] == user and r['resolved_by'] in (user, None)

    # idempotent: a second pass finds nothing left to anonymise
    assert await repository.anonymise_resolved_alerts(migrated_conn, DAYS) == 0
    # the alert-out join still works with the NULLs (name unknown)
    out = await repository.get_alert_out(migrated_conn, str(old))
    assert out.user_id is None and out.full_name is None and out.device_id is None


@pytest.mark.Trait("Bug", "B48")
@pytest.mark.asyncio
async def test_cleanup_logs_count_only_and_anonymise_error_does_not_skip_location_prune(monkeypatch, caplog):
    from backend.modules.fire import tasks as fire_tasks
    from backend.modules.tracking import tasks as tracking_tasks

    calls = []

    class _Conn:
        async def fetchval(self, *a, **k):
            calls.append('location')
            return 3

    class _Acquire:
        async def __aenter__(self):
            return _Conn()

        async def __aexit__(self, *a):
            return False

    class _Pool:
        def acquire(self):
            return _Acquire()

    async def boom(_conn, _days):
        raise RuntimeError('anonymise exploded')

    async def fire_prune(_conn):
        calls.append('fire')
        return {'fire_hotspots': 0, 'fire_burnt_areas': 0}

    monkeypatch.setattr(tracking_tasks, 'get_pool', lambda: _Pool())
    monkeypatch.setattr(fire_tasks, 'get_pool', lambda: _Pool())
    monkeypatch.setattr(fire_tasks.repository, 'anonymise_alerts', boom)
    monkeypatch.setattr(fire_tasks.repository, 'anonymise_hotspots', _no_hotspots)
    monkeypatch.setattr(fire_tasks.repository, 'prune_fire_data', fire_prune)
    with caplog.at_level('INFO'):
        await tracking_tasks.cleanup_positions_once()
        await fire_tasks.cleanup_fire_data_once()
    messages = [r.getMessage() for r in caplog.records]
    assert calls == ['location', 'fire']
    assert any(m == 'Fire alert anonymisation failed: anonymise exploded' for m in messages)
    assert not any('Location cleanup failed' in m for m in messages)


@pytest.mark.Trait("Bug", "B48")
@pytest.mark.asyncio
async def test_cleanup_logs_the_anonymised_count(monkeypatch, caplog):
    from backend.modules.fire import tasks as fire_tasks
    from backend.modules.tracking import tasks as tracking_tasks

    class _Conn:
        async def fetchval(self, *a, **k):
            return 0

    class _Acquire:
        async def __aenter__(self):
            return _Conn()

        async def __aexit__(self, *a):
            return False

    class _Pool:
        def acquire(self):
            return _Acquire()

    seen = []

    async def fake_anon(_conn, days):
        seen.append(days)
        return 4

    async def fire_prune(_conn):
        return {'fire_hotspots': 0, 'fire_burnt_areas': 0}

    monkeypatch.setattr(tracking_tasks, 'get_pool', lambda: _Pool())
    monkeypatch.setattr(fire_tasks, 'get_pool', lambda: _Pool())
    monkeypatch.setattr(fire_tasks.repository, 'anonymise_alerts', fake_anon)
    monkeypatch.setattr(fire_tasks.repository, 'anonymise_hotspots', _no_hotspots)
    monkeypatch.setattr(fire_tasks.repository, 'prune_fire_data', fire_prune)
    with caplog.at_level('INFO'):
        await tracking_tasks.cleanup_positions_once()
        await fire_tasks.cleanup_fire_data_once()
    assert seen == [tracking_tasks.settings.location_retention_days]
    assert any(r.getMessage() == 'Fire alert anonymisation: anonymised 4 resolved alerts' for r in caplog.records)


def _b55_run(monkeypatch, caplog, *, alerts, hotspots):
    """Run one cleanup pass with the two anonymisation steps replaced; returns (log messages, calls)."""
    from backend.modules.fire import tasks as fire_tasks
    from backend.modules.tracking import tasks as tracking_tasks

    calls = []

    class _Conn:
        async def fetchval(self, *a, **k):
            calls.append('location')
            return 3

    class _Acquire:
        async def __aenter__(self):
            return _Conn()

        async def __aexit__(self, *a):
            return False

    class _Pool:
        def acquire(self):
            return _Acquire()

    async def fire_prune(_conn):
        calls.append('fire')
        return {'fire_hotspots': 0, 'fire_burnt_areas': 0, 'fire_suppression_zones': 0}

    monkeypatch.setattr(tracking_tasks, 'get_pool', lambda: _Pool())
    monkeypatch.setattr(fire_tasks, 'get_pool', lambda: _Pool())
    monkeypatch.setattr(fire_tasks.repository, 'anonymise_alerts', alerts)
    monkeypatch.setattr(fire_tasks.repository, 'anonymise_hotspots', hotspots)
    monkeypatch.setattr(fire_tasks.repository, 'prune_fire_data', fire_prune)

    async def go():
        with caplog.at_level('INFO'):
            await tracking_tasks.cleanup_positions_once()
            await fire_tasks.cleanup_fire_data_once()

    return go, calls


@pytest.mark.Trait("Bug", "B55")
@pytest.mark.asyncio
async def test_hotspot_step_failure_has_its_own_message_and_alert_count_is_logged(monkeypatch, caplog):
    async def alerts(_conn, _days):
        return 4

    async def hotspots(_conn, _days):
        raise RuntimeError('hotspot exploded')

    go, calls = _b55_run(monkeypatch, caplog, alerts=alerts, hotspots=hotspots)
    await go()
    messages = [r.getMessage() for r in caplog.records]
    assert 'Fire alert anonymisation: anonymised 4 resolved alerts' in messages
    assert 'Fire hotspot anonymisation failed: hotspot exploded' in messages
    assert not any(m.startswith('Fire alert anonymisation failed') for m in messages)
    assert calls == ['location', 'fire']


@pytest.mark.Trait("Bug", "B55")
@pytest.mark.asyncio
async def test_alert_step_failure_does_not_skip_hotspots_location_or_fire_prune(monkeypatch, caplog):
    async def alerts(_conn, _days):
        raise RuntimeError('alerts exploded')

    async def hotspots(_conn, _days):
        return 2

    go, calls = _b55_run(monkeypatch, caplog, alerts=alerts, hotspots=hotspots)
    await go()
    messages = [r.getMessage() for r in caplog.records]
    assert 'Fire alert anonymisation failed: alerts exploded' in messages
    assert 'Fire hotspot anonymisation: anonymised 2 hotspots' in messages
    assert any(m.startswith('Location cleanup: removed 3 events') for m in messages)
    assert calls == ['location', 'fire']
