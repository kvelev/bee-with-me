"""Refresh cycle against a real (scratch) database with fixture sources."""

import asyncio
import json
from datetime import datetime, timedelta, timezone

import asyncpg
import pytest
import pytest_asyncio

from backend.fire import poller, repository
from backend.fire.parse import HotspotRow
from backend.fire.sources import FeedFetchError, FixtureSource

pytestmark = [pytest.mark.Trait("Task", "T9"), pytest.mark.db, pytest.mark.asyncio]

NOW = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)


async def _no_hotspots(_conn, _days):
    return 0


def _hotspots(*items):
    return {'type': 'FeatureCollection', 'features': [
        {'type': 'Feature', 'properties': {'id': i, 'acq_at': acq, 'CLASS': '1DAY_N'},
         'geometry': {'type': 'Point', 'coordinates': [lon, lat]}} for i, lat, lon, acq in items]}


AREAS = {'type': 'FeatureCollection', 'features': [
    {'type': 'Feature', 'properties': {'id': 'b1', 'fire_id': 'f1', 'initialdate': '2026-09-30 10:38:00',
                                       'finaldate': '2026-09-30 13:44:00', 'area': '196'},
     'geometry': {'type': 'Polygon', 'coordinates': [[[24, 42], [24.1, 42], [24.1, 42.1], [24, 42]]]}}]}


@pytest_asyncio.fixture()
async def pool(migrated_conn, scratch_db):
    p = await asyncpg.create_pool(**scratch_db, min_size=1, max_size=3)
    poller.FEEDS['hotspots'] = poller.FeedState()
    poller.FEEDS['burnt_areas'] = poller.FeedState()
    yield p
    await p.close()


async def test_refresh_stores_both_feeds_and_reports_live(pool, migrated_conn):
    hs = FixtureSource('hotspots', _hotspots(('h1', 42.5, 24.5, '2026-10-02 10:00:00')))
    assert await poller.refresh_once(pool, hs, FixtureSource('burnt_areas', AREAS), now=lambda: NOW)
    assert await migrated_conn.fetchval('SELECT count(*) FROM fire_hotspots') == 1
    assert await migrated_conn.fetchval('SELECT count(*) FROM fire_burnt_areas') == 1
    assert await migrated_conn.fetchval('SELECT h3_r8 FROM fire_hotspots') is not None
    assert poller.FEEDS['hotspots'].upstream_state == 'live'
    assert poller.FEEDS['hotspots'].last_success_at == NOW
    assert poller.FEEDS['burnt_areas'].count == 1


async def test_upsert_updates_upstream_fields_but_never_admin_state(pool, migrated_conn):
    first = FixtureSource('hotspots', _hotspots(('h1', 42.5, 24.5, '2026-10-02 10:00:00')))
    await poller.refresh_once(pool, first, FixtureSource('burnt_areas', AREAS), now=lambda: NOW)
    await migrated_conn.execute(
        "UPDATE fire_hotspots SET dismissed_at = NOW(), dismiss_notes = 'solar park', notes = 'n', "
        "last_seen_at = NOW() - INTERVAL '1 hour'")
    second = FixtureSource('hotspots', _hotspots(('h1', 42.6, 24.6, '2026-10-02 11:00:00')))
    await poller.refresh_once(pool, second, FixtureSource('burnt_areas', AREAS), now=lambda: NOW)
    row = await migrated_conn.fetchrow('SELECT * FROM fire_hotspots')
    assert (row['latitude'], row['longitude']) == (42.6, 24.6)
    assert row['dismissed_at'] is not None and row['dismiss_notes'] == 'solar park' and row['notes'] == 'n'
    assert row['last_seen_at'] > row['first_seen_at']


async def test_failing_feed_keeps_data_and_reports_error(pool, migrated_conn):
    good = FixtureSource('hotspots', _hotspots(('h1', 42.5, 24.5, '2026-10-02 10:00:00')))
    await poller.refresh_once(pool, good, FixtureSource('burnt_areas', AREAS), now=lambda: NOW)
    bad = FixtureSource('hotspots', error=FeedFetchError('hotspots: HTTP 502'))
    garbage = FixtureSource('burnt_areas', '<html>')
    await poller.refresh_once(pool, bad, garbage, now=lambda: NOW)
    assert await migrated_conn.fetchval('SELECT count(*) FROM fire_hotspots') == 1
    assert await migrated_conn.fetchval('SELECT count(*) FROM fire_burnt_areas') == 1
    assert poller.FEEDS['hotspots'].upstream_state == 'error'
    assert 'HTTP 502' in poller.FEEDS['hotspots'].last_error
    assert poller.FEEDS['burnt_areas'].upstream_state == 'error'
    assert poller.FEEDS['hotspots'].last_success_at == NOW


async def test_quiet_week_is_not_an_error(pool):
    old = FixtureSource('hotspots', _hotspots(('h1', 42.5, 24.5, '2026-09-27 10:00:00')))
    await poller.refresh_once(pool, old, FixtureSource('burnt_areas', AREAS), now=lambda: NOW)
    assert poller.FEEDS['hotspots'].upstream_state == 'no_recent_detections'
    assert poller.FEEDS['hotspots'].last_error is None


async def test_second_process_skips_while_lock_is_held(pool, scratch_db):
    holder = await asyncpg.connect(**scratch_db)
    try:
        await holder.execute('SELECT pg_advisory_lock($1)', poller.REFRESH_LOCK_KEY)
        hs = FixtureSource('hotspots', _hotspots(('h1', 42.5, 24.5, '2026-10-02 10:00:00')))
        assert await poller.refresh_once(pool, hs, FixtureSource('burnt_areas', AREAS), now=lambda: NOW) is False
    finally:
        await holder.close()


async def test_refresh_notifies_fire_data_updated(pool, scratch_db):
    received = asyncio.Queue()
    listener = await asyncpg.connect(**scratch_db)
    await listener.add_listener('fire_data_updated', lambda *a: received.put_nowait(a[3]))
    try:
        hs = FixtureSource('hotspots', _hotspots(('h1', 42.5, 24.5, '2026-10-02 10:00:00')))
        await poller.refresh_once(pool, hs, FixtureSource('burnt_areas', AREAS), now=lambda: NOW)
        payload = json.loads(await asyncio.wait_for(received.get(), timeout=3))
    finally:
        await listener.close()
    assert payload == {'fetched_at': NOW.isoformat(), 'hotspot_count': 1,
                       'burnt_area_count': 1, 'upstream_state': 'live'}


async def test_prune_removes_only_rows_unseen_for_7_days(pool, migrated_conn):
    rows = [HotspotRow('viirs', 'old', NOW, 42.5, 24.5, None), HotspotRow('viirs', 'new', NOW, 42.5, 24.5, None)]
    await repository.upsert_hotspots(migrated_conn, rows)
    await migrated_conn.execute("UPDATE fire_hotspots SET last_seen_at = NOW() - INTERVAL '8 days' WHERE effis_id = 'old'")
    await migrated_conn.execute(
        "INSERT INTO fire_hotspots (source, effis_id, acquired_at, latitude, longitude) "
        "VALUES ('field_report', NULL, NOW() - INTERVAL '8 days', 42.5, 24.5)")
    deleted = await repository.prune_fire_data(migrated_conn)
    assert deleted['fire_hotspots'] == 2
    assert [r['effis_id'] for r in await migrated_conn.fetch('SELECT effis_id FROM fire_hotspots')] == ['new']


@pytest.mark.Trait("Bug", "B40")
async def test_prune_skips_alerted_hotspots_and_still_prunes_the_rest(pool, migrated_conn):
    await repository.upsert_hotspots(migrated_conn, [HotspotRow('viirs', 'alerted', NOW, 42.5, 24.5, None),
                                                     HotspotRow('viirs', 'plain', NOW, 42.5, 24.5, None)])
    await migrated_conn.execute("UPDATE fire_hotspots SET last_seen_at = NOW() - INTERVAL '8 days'")
    await migrated_conn.execute(
        "INSERT INTO fire_alerts (hotspot_id, target_type, distance_m) "
        "SELECT id, 'hq', 100 FROM fire_hotspots WHERE effis_id = 'alerted'")
    deleted = await repository.prune_fire_data(migrated_conn)
    assert deleted['fire_hotspots'] == 1
    assert [r['effis_id'] for r in await migrated_conn.fetch('SELECT effis_id FROM fire_hotspots')] == ['alerted']


async def test_last_seen_at_survives_restart(pool, migrated_conn):
    await repository.upsert_hotspots(migrated_conn, [HotspotRow('viirs', 'x', NOW, 42.5, 24.5, None)])
    assert await repository.last_seen_at(migrated_conn, 'fire_hotspots') is not None
    with pytest.raises(ValueError):
        await repository.last_seen_at(migrated_conn, 'users; DROP TABLE users')


# ---- B26: per-feed deadline, catch-all per feed, separate fire prune errors ----

class _SlowSource:
    async def fetch(self):
        await asyncio.sleep(30)


class _RaisingSource:
    def __init__(self, exc):
        self._exc = exc

    async def fetch(self):
        raise self._exc


@pytest.mark.Trait("Bug", "B26")
async def test_slow_feed_hits_deadline_and_other_feed_still_refreshes(pool, migrated_conn, monkeypatch):
    monkeypatch.setattr(poller, 'FEED_DEADLINE_S', 0.05)
    await poller.refresh_once(pool, _SlowSource(), FixtureSource('burnt_areas', AREAS), now=lambda: NOW)
    assert poller.FEEDS['hotspots'].upstream_state == 'error'
    assert 'deadline' in poller.FEEDS['hotspots'].last_error
    assert poller.FEEDS['burnt_areas'].upstream_state == 'live'
    assert await migrated_conn.fetchval('SELECT count(*) FROM fire_burnt_areas') == 1


@pytest.mark.Trait("Bug", "B26")
@pytest.mark.parametrize('exc', [RecursionError('too deep'), ValueError('shape'), TypeError('shape')])
async def test_unexpected_source_error_is_contained_per_feed(pool, migrated_conn, exc):
    hs = _RaisingSource(exc)
    assert await poller.refresh_once(pool, hs, FixtureSource('burnt_areas', AREAS), now=lambda: NOW)
    assert poller.FEEDS['hotspots'].upstream_state == 'error'
    assert poller.FEEDS['hotspots'].last_error
    assert poller.FEEDS['burnt_areas'].upstream_state == 'live'
    assert await migrated_conn.fetchval('SELECT count(*) FROM fire_burnt_areas') == 1


@pytest.mark.Trait("Bug", "B26")
async def test_cancelled_error_from_source_propagates(pool, migrated_conn, scratch_db):
    with pytest.raises(asyncio.CancelledError):
        await poller.refresh_once(pool, _RaisingSource(asyncio.CancelledError()),
                                  FixtureSource('burnt_areas', AREAS), now=lambda: NOW)
    # the advisory lock must have been released on the way out
    other = await asyncpg.connect(**scratch_db)
    try:
        assert await other.fetchval('SELECT pg_try_advisory_lock($1)', poller.REFRESH_LOCK_KEY)
    finally:
        await other.close()


@pytest.mark.Trait("Bug", "B26")
async def test_fire_prune_failure_has_own_message_and_location_prune_ran(monkeypatch, caplog):
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

    async def boom(_conn):
        raise RuntimeError('fire prune exploded')

    monkeypatch.setattr(tracking_tasks, 'get_pool', lambda: _Pool())
    monkeypatch.setattr(fire_tasks, 'get_pool', lambda: _Pool())
    async def no_anonymise(_conn, _days):
        return 0

    monkeypatch.setattr(fire_tasks.repository, 'anonymise_alerts', no_anonymise)
    monkeypatch.setattr(fire_tasks.repository, 'anonymise_hotspots', _no_hotspots)
    monkeypatch.setattr(fire_tasks.repository, 'prune_fire_data', boom)
    with caplog.at_level('INFO'):
        await tracking_tasks.cleanup_positions_once()
        await fire_tasks.cleanup_fire_data_once()
    messages = [r.getMessage() for r in caplog.records]
    assert calls == ['location']
    assert any(m.startswith('Location cleanup: removed 3 events') for m in messages)
    assert any(m == 'Fire data prune failed: fire prune exploded' for m in messages)
    assert not any('Location cleanup failed' in m for m in messages)


def _renamed_field_hotspots(n=3):
    return {'type': 'FeatureCollection', 'features': [
        {'type': 'Feature', 'properties': {'id': 'r%d' % i, 'acq_date': '2026-10-02 10:00:00'},
         'geometry': {'type': 'Point', 'coordinates': [24.5, 42.5]}} for i in range(n)]}


@pytest.mark.Trait("Bug", "B28")
async def test_renamed_field_gives_error_state_and_leaves_stored_rows(pool, migrated_conn):
    good = FixtureSource('hotspots', _hotspots(('h1', 42.5, 24.5, '2026-10-02 10:00:00')))
    await poller.refresh_once(pool, good, FixtureSource('burnt_areas', AREAS), now=lambda: NOW)
    changed = FixtureSource('hotspots', _renamed_field_hotspots(3))
    await poller.refresh_once(pool, changed, FixtureSource('burnt_areas', AREAS), now=lambda: NOW)
    state = poller.FEEDS['hotspots']
    assert state.upstream_state == 'error'
    assert state.last_error == '3 of 3 features unusable (format changed?)'
    assert state.last_success_at == NOW and state.count == 1
    assert [r['effis_id'] for r in await migrated_conn.fetch('SELECT effis_id FROM fire_hotspots')] == ['h1']
    assert poller.FEEDS['burnt_areas'].upstream_state == 'live'


@pytest.mark.Trait("Bug", "B28")
async def test_more_than_half_dropped_is_an_error_but_a_minority_is_not(pool, migrated_conn):
    def mixed(bad):
        feats = _hotspots(*[('g%d' % i, 42.5, 24.5, '2026-10-02 10:00:00') for i in range(4 - bad)])
        feats['features'] += _renamed_field_hotspots(bad)['features']
        return feats
    await poller.refresh_once(pool, FixtureSource('hotspots', mixed(3)), FixtureSource('burnt_areas', AREAS),
                              now=lambda: NOW)
    assert poller.FEEDS['hotspots'].upstream_state == 'error'
    assert await migrated_conn.fetchval('SELECT count(*) FROM fire_hotspots') == 0
    await poller.refresh_once(pool, FixtureSource('hotspots', mixed(1)), FixtureSource('burnt_areas', AREAS),
                              now=lambda: NOW)
    assert poller.FEEDS['hotspots'].upstream_state == 'live'
    assert await migrated_conn.fetchval('SELECT count(*) FROM fire_hotspots') == 3


@pytest.mark.Trait("Bug", "B28")
async def test_empty_collection_is_still_a_quiet_week_not_an_error(pool):
    await poller.refresh_once(pool, FixtureSource('hotspots', _hotspots()), FixtureSource('burnt_areas', AREAS),
                              now=lambda: NOW)
    assert poller.FEEDS['hotspots'].upstream_state == 'no_recent_detections'
    assert poller.FEEDS['hotspots'].last_error is None


@pytest.mark.Trait("Bug", "B28")
async def test_full_count_response_logs_truncation_and_notes_it(pool, caplog):
    limit = poller.FEATURE_LIMIT
    big = _hotspots(*[('t%d' % i, 42.5, 24.5, '2026-10-02 10:00:00') for i in range(limit)])
    with caplog.at_level('WARNING'):
        await poller.refresh_once(pool, FixtureSource('hotspots', big), FixtureSource('burnt_areas', AREAS),
                                  now=lambda: NOW)
    state = poller.FEEDS['hotspots']
    assert state.upstream_state == 'live' and state.count == limit
    assert 'truncated' in state.last_error
    assert 'probably truncated' in caplog.text


# ---- B30: no connection or lock held during the network fetch; explicit unlock ----

class _ProbingSource:
    """Records how many pool connections are checked out while fetch() runs."""

    def __init__(self, pool, payload):
        self._pool, self._payload, self.checked_out = pool, payload, []

    async def fetch(self):
        self.checked_out.append(self._pool.get_size() - self._pool.get_idle_size())
        return self._payload


@pytest.mark.Trait("Bug", "B30")
async def test_no_pool_connection_is_held_while_fetching(pool):
    hs = _ProbingSource(pool, _hotspots(('h1', 42.5, 24.5, '2026-10-02 10:00:00')))
    ba = _ProbingSource(pool, AREAS)
    assert await poller.refresh_once(pool, hs, ba, now=lambda: NOW)
    assert hs.checked_out == [0] and ba.checked_out == [0]
    assert poller.FEEDS['hotspots'].upstream_state == 'live'


@pytest.mark.Trait("Bug", "B30")
async def test_advisory_lock_is_free_while_fetching(pool, scratch_db):
    holder = await asyncpg.connect(**scratch_db)
    seen = []
    try:
        class _LockProbe:
            async def fetch(self):
                got = await holder.fetchval('SELECT pg_try_advisory_lock($1)', poller.REFRESH_LOCK_KEY)
                if got:
                    await holder.execute('SELECT pg_advisory_unlock($1)', poller.REFRESH_LOCK_KEY)
                seen.append(got)
                return _hotspots()

        await poller.refresh_once(pool, _LockProbe(), FixtureSource('burnt_areas', AREAS), now=lambda: NOW)
        assert seen == [True]
    finally:
        await holder.close()


class _CheckedOutPool:
    """Before the pool takes the connection back, asks another session whether the refresh lock is free.

    asyncpg resets a released connection (pg_advisory_unlock_all), which would hide a missing explicit unlock.
    """

    def __init__(self, pool, probe):
        self._pool, self._probe, self.lock_free_at_release = pool, probe, []

    def acquire(self):
        outer = self
        inner = self._pool.acquire()

        class _Ctx:
            async def __aenter__(self):
                return await inner.__aenter__()

            async def __aexit__(self, *exc):
                got = await outer._probe.fetchval('SELECT pg_try_advisory_lock($1)', poller.REFRESH_LOCK_KEY)
                if got:
                    await outer._probe.execute('SELECT pg_advisory_unlock($1)', poller.REFRESH_LOCK_KEY)
                outer.lock_free_at_release.append(got)
                return await inner.__aexit__(*exc)

        return _Ctx()


@pytest.mark.Trait("Bug", "B30")
async def test_lock_is_explicitly_unlocked_before_the_connection_is_released(pool, scratch_db):
    probe = await asyncpg.connect(**scratch_db)
    try:
        checking = _CheckedOutPool(pool, probe)
        hs = FixtureSource('hotspots', _hotspots(('h1', 42.5, 24.5, '2026-10-02 10:00:00')))
        assert await poller.refresh_once(checking, hs, FixtureSource('burnt_areas', AREAS), now=lambda: NOW)
        assert checking.lock_free_at_release == [True]
    finally:
        await probe.close()


@pytest.mark.Trait("Bug", "B30")
async def test_lock_is_released_when_the_store_phase_is_cancelled(pool, scratch_db, monkeypatch):
    probe = await asyncpg.connect(**scratch_db)
    try:
        async def cancelled(conn, rows):
            raise asyncio.CancelledError

        monkeypatch.setattr(repository, 'upsert_hotspots', cancelled)
        checking = _CheckedOutPool(pool, probe)
        hs = FixtureSource('hotspots', _hotspots(('h1', 42.5, 24.5, '2026-10-02 10:00:00')))
        with pytest.raises(asyncio.CancelledError):
            await poller.refresh_once(checking, hs, FixtureSource('burnt_areas', AREAS), now=lambda: NOW)
        assert checking.lock_free_at_release == [True]
    finally:
        await probe.close()


@pytest.mark.Trait("Bug", "B30")
async def test_only_one_refresh_runs_at_a_time_in_this_process(pool):
    started, release = asyncio.Event(), asyncio.Event()

    class _Blocking:
        async def fetch(self):
            started.set()
            await release.wait()
            return _hotspots()

    first = asyncio.create_task(
        poller.refresh_once(pool, _Blocking(), FixtureSource('burnt_areas', AREAS), now=lambda: NOW))
    await asyncio.wait_for(started.wait(), timeout=3)
    second = await poller.refresh_once(pool, FixtureSource('hotspots', _hotspots()),
                                       FixtureSource('burnt_areas', AREAS), now=lambda: NOW)
    release.set()
    assert second is False
    assert await asyncio.wait_for(first, timeout=5) is True


@pytest.mark.Trait("Bug", "B31")
async def test_exactly_half_dropped_is_not_an_error(pool, migrated_conn):
    feats = _hotspots(('g1', 42.5, 24.5, '2026-10-02 10:00:00'), ('g2', 42.5, 24.5, '2026-10-02 10:00:00'))
    feats['features'] += _renamed_field_hotspots(2)['features']          # 2 of 4 dropped
    await poller.refresh_once(pool, FixtureSource('hotspots', feats), FixtureSource('burnt_areas', AREAS),
                              now=lambda: NOW)
    assert poller.FEEDS['hotspots'].upstream_state == 'live'
    assert await migrated_conn.fetchval('SELECT count(*) FROM fire_hotspots') == 2


@pytest.mark.Trait("Bug", "B31")
async def test_mostly_future_drop_points_at_the_machine_clock(pool, migrated_conn):
    feats = _hotspots(('g1', 42.5, 24.5, '2026-10-02 10:00:00'),
                      *[('f%d' % i, 42.5, 24.5, '2026-10-05 10:00:00') for i in range(3)])
    await poller.refresh_once(pool, FixtureSource('hotspots', feats), FixtureSource('burnt_areas', AREAS),
                              now=lambda: NOW)
    state = poller.FEEDS['hotspots']
    assert state.upstream_state == 'error'
    assert state.last_error == '3 of 4 features unusable (mostly future: check the machine clock)'
    assert await migrated_conn.fetchval('SELECT count(*) FROM fire_hotspots') == 0
