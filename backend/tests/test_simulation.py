"""
Test mode (backend/simulation.py + /api/test/simulation*) and INITIAL_ADMIN_PASSWORD.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from backend import main, simulation as sim
from backend.auth import verify_password


@pytest.fixture(autouse=True)
def fresh_simulation(monkeypatch):
    """Every test gets its own Simulation instead of the process-wide singleton."""
    monkeypatch.setattr(sim, 'simulation', sim.Simulation())
    yield
    task = sim.simulation.task
    if task is not None and not task.done():
        task.cancel()


# ── Endpoints (no database) ───────────────────────────────────────────────────

class _Pool:
    def acquire(self):
        return self

    async def __aenter__(self):
        return object()

    async def __aexit__(self, *exc):
        return False


def test_status_when_idle(client):
    resp = client.get('/api/test/simulation')
    assert resp.status_code == 200
    assert resp.json()['running'] is False


def test_start_twice_is_409_and_stop_ends_it(client, monkeypatch):
    async def _forever(self, devices):
        await asyncio.Event().wait()

    monkeypatch.setattr(sim, 'get_pool', lambda: _Pool())
    monkeypatch.setattr(sim.Simulation, '_run', _forever)
    with patch.object(sim, 'seed', AsyncMock(return_value={'demo_ivan': {'id': 1, 'user_id': 2}})):
        first = client.post('/api/test/simulation/start', json={'lat': 42.1, 'lon': 24.7, 'interval': 2})
        assert first.status_code == 200
        assert first.json()['running'] is True and first.json()['devices'] == 1
        assert client.post('/api/test/simulation/start', json={}).status_code == 409
    stopped = client.post('/api/test/simulation/stop')
    assert stopped.status_code == 200 and stopped.json()['running'] is False


@pytest.mark.parametrize('body', [
    {'interval': 0.1}, {'interval': 600}, {'lat': 91}, {'lon': -181},
    {'trackers': 0}, {'trackers': 13}, {'step_m': 1}, {'spread_km': 100},
    {'trackers': 3, 'sos': 2, 'lost': 2},          # more states than trackers
    {'trackers': 2, 'low_battery': 3},
])
def test_start_rejects_out_of_range_input(client, body):
    assert client.post('/api/test/simulation/start', json=body).status_code == 422


# ── On a real database ────────────────────────────────────────────────────────

@pytest.mark.db
@pytest.mark.asyncio
async def test_seed_is_idempotent_and_copies_photos(migrated_conn, tmp_path, monkeypatch):
    monkeypatch.setattr(sim, 'UPLOADS_DIR', tmp_path)
    first = await sim.seed(migrated_conn)
    second = await sim.seed(migrated_conn)
    assert len(first) == 6   # the default: the six personas
    assert {u: d['id'] for u, d in first.items()} == {u: d['id'] for u, d in second.items()}
    assert await migrated_conn.fetchval("SELECT count(*) FROM users WHERE username LIKE 'demo_%'") == 6
    assert await migrated_conn.fetchval('SELECT count(*) FROM devices WHERE dev_sn BETWEEN 9001 AND 9006') == 6
    assert await migrated_conn.fetchval("SELECT count(*) FROM groups WHERE name IN ('Alpha Team','Bravo Team')") == 2
    photos = await migrated_conn.fetch("SELECT photo_url FROM users WHERE username LIKE 'demo_%'")
    assert all(r['photo_url'] for r in photos)
    assert len(list(tmp_path.iterdir())) == 6   # copied once, not again on the second seed
    # demo volunteers are map markers, not accounts: no guessable password
    for row in await migrated_conn.fetch("SELECT password_hash FROM users WHERE username LIKE 'demo_%'"):
        assert not verify_password('demo123', row['password_hash'])


@pytest.mark.db
@pytest.mark.asyncio
async def test_seed_reactivates_and_reassigns(migrated_conn, tmp_path, monkeypatch):
    monkeypatch.setattr(sim, 'UPLOADS_DIR', tmp_path)
    devices = await sim.seed(migrated_conn)
    await migrated_conn.execute("UPDATE users SET is_active = FALSE WHERE username = 'demo_ivan'")
    await migrated_conn.execute('UPDATE devices SET is_active = FALSE, user_id = NULL WHERE dev_sn = 9001')
    again = await sim.seed(migrated_conn)
    assert again['demo_ivan']['id'] == devices['demo_ivan']['id']
    assert again['demo_ivan']['user_id'] == devices['demo_ivan']['user_id']
    assert await migrated_conn.fetchval("SELECT is_active FROM users WHERE username = 'demo_ivan'") is True
    assert await migrated_conn.fetchval('SELECT is_active FROM devices WHERE dev_sn = 9001') is True


@pytest.mark.db
@pytest.mark.asyncio
async def test_running_simulation_writes_positions_and_sos(scratch_pool, migrated_conn, tmp_path, monkeypatch):
    monkeypatch.setattr(sim, 'UPLOADS_DIR', tmp_path)
    monkeypatch.setattr(sim, 'get_pool', lambda: scratch_pool)
    status = await sim.simulation.start(42.698, 23.322, 1)
    assert status['running'] is True and status['devices'] == 6
    for _ in range(50):
        if sim.simulation.steps >= 1:
            break
        await asyncio.sleep(0.1)
    stopped = await sim.simulation.stop()
    assert stopped['running'] is False and stopped['steps'] >= 1 and stopped['last_error'] is None
    assert await migrated_conn.fetchval('SELECT count(DISTINCT device_id) FROM location_events') == 6
    assert await migrated_conn.fetchval(
        """SELECT count(*) FROM sos_alerts a JOIN devices d ON d.id = a.device_id
           WHERE d.dev_sn = 9004 AND a.resolved_at IS NULL""") == 1


@pytest.mark.db
@pytest.mark.asyncio
@pytest.mark.parametrize('configured, expected', [('Str0ng-and-l0ng', 'Str0ng-and-l0ng'), ('', 'admin')])
async def test_default_admin_uses_initial_admin_password(scratch_pool, migrated_conn, monkeypatch, configured, expected):
    monkeypatch.setattr(main, 'get_pool', lambda: scratch_pool)
    monkeypatch.setattr(main.settings, 'initial_admin_password', configured)
    await main._ensure_default_admin()
    pw_hash = await migrated_conn.fetchval("SELECT password_hash FROM users WHERE username = 'admin'")
    assert verify_password(expected, pw_hash)
    if configured:
        assert not verify_password('admin', pw_hash)


@pytest.mark.db
@pytest.mark.asyncio
async def test_initial_admin_password_is_applied_once_never_on_later_starts(scratch_pool, migrated_conn, monkeypatch):
    """A redeploy (backend restart) must not reset the admin password — neither to the configured
    value after the admin changed it in the app, nor when INITIAL_ADMIN_PASSWORD itself changes."""
    from backend.auth import hash_password
    monkeypatch.setattr(main, 'get_pool', lambda: scratch_pool)
    monkeypatch.setattr(main.settings, 'initial_admin_password', 'First-start-pw')
    await main._ensure_default_admin()

    # the admin changes the password in the app
    await migrated_conn.execute("UPDATE users SET password_hash = $1 WHERE username = 'admin'",
                                hash_password('Changed-in-the-app'))
    # later starts, with the same and then a different configured value
    await main._ensure_default_admin()
    monkeypatch.setattr(main.settings, 'initial_admin_password', 'Rotated-secret')
    await main._ensure_default_admin()

    pw_hash = await migrated_conn.fetchval("SELECT password_hash FROM users WHERE username = 'admin'")
    assert verify_password('Changed-in-the-app', pw_hash)
    assert await migrated_conn.fetchval("SELECT count(*) FROM users WHERE username = 'admin'") == 1


def test_start_passes_the_scenario(client, monkeypatch):
    seen = {}

    async def _start(self, lat, lon, interval, scenario=None):
        seen.update(lat=lat, interval=interval, scenario=scenario)
        return {'running': True}

    monkeypatch.setattr(sim.Simulation, 'start', _start)
    r = client.post('/api/test/simulation/start', json={
        'lat': 42.1, 'interval': 2, 'trackers': 10, 'sos': 2, 'no_fix': 1, 'stale': 1, 'lost': 1,
        'low_battery': 3, 'step_m': 50, 'spread_km': 1.5})
    assert r.status_code == 200
    assert seen['scenario'] == sim.Scenario(trackers=10, sos=2, no_fix=1, stale=1, lost=1,
                                            low_battery=3, step_m=50, spread_km=1.5)


def test_roles_put_the_sos_persona_first_and_fill_in_order():
    names = [u['username'] for u in sim.DEMO_USERS[:6]]
    roles = sim.Scenario(trackers=6, sos=1, no_fix=1, stale=1, lost=1).roles(names)
    assert roles['demo_elena'] == 'sos'
    assert sorted(roles.values()) == ['lost', 'moving', 'moving', 'no_fix', 'sos', 'stale']


@pytest.mark.db
@pytest.mark.asyncio
async def test_scenario_produces_every_state(scratch_pool, migrated_conn, tmp_path, monkeypatch):
    monkeypatch.setattr(sim, 'UPLOADS_DIR', tmp_path)
    monkeypatch.setattr(sim, 'get_pool', lambda: scratch_pool)
    scenario = sim.Scenario(trackers=9, sos=2, no_fix=1, stale=1, lost=1, low_battery=2, step_m=50, spread_km=1)
    await sim.simulation.start(42.698, 23.322, 1, scenario)
    roles = sim.simulation._roles
    for _ in range(80):
        if sim.simulation.steps >= 2:
            break
        await asyncio.sleep(0.1)
    status = await sim.simulation.stop()
    assert status['devices'] == 9 and status['last_error'] is None and status['scenario']['sos'] == 2

    rows = await migrated_conn.fetch(
        """SELECT u.username, count(*) AS n, bool_and(le.gnss_valid) AS all_fix, bool_or(NOT le.gnss_valid) AS any_nofix,
                  max(now() - le.received_at) AS oldest, min(now() - le.received_at) AS newest,
                  max(le.battery_voltage) AS max_bat
           FROM location_events le JOIN devices d ON d.id = le.device_id JOIN users u ON u.id = d.user_id
           GROUP BY u.username""")
    by = {r['username']: r for r in rows}
    assert len(by) == 9                                            # 6 personas + 3 extras
    assert await migrated_conn.fetchval('SELECT count(*) FROM devices WHERE dev_sn BETWEEN 9007 AND 9012') == 3
    role_of = {r: [u for u, x in roles.items() if x == r] for r in ('sos', 'no_fix', 'stale', 'lost', 'moving')}
    stale, lost, nofix = role_of['stale'][0], role_of['lost'][0], role_of['no_fix'][0]
    assert by[stale]['n'] == 1 and 14 * 60 <= by[stale]['newest'].total_seconds() <= 16 * 60
    assert by[lost]['n'] == 1 and 44 * 60 <= by[lost]['newest'].total_seconds() <= 46 * 60
    assert by[nofix]['any_nofix'] and by[nofix]['n'] >= 2         # one anchoring fix, then no-fix frames
    anchored = await migrated_conn.fetch(
        """SELECT DISTINCT latitude, longitude FROM location_events le JOIN devices d ON d.id = le.device_id
           JOIN users u ON u.id = d.user_id WHERE u.username = $1""", nofix)
    assert len(anchored) == 1                                      # no-fix frames stay at the last fix
    for u in role_of['moving'] + role_of['sos']:
        assert by[u]['all_fix'] and by[u]['newest'].total_seconds() < 60
    assert await migrated_conn.fetchval('SELECT count(*) FROM sos_alerts WHERE resolved_at IS NULL') == 2
    low = sim.simulation._low_battery
    # battery_voltage is REAL (float4): 3.40 reads back as 3.4000000953..., so round before comparing
    assert len(low) == 2 and all(round(by[u]['max_bat'], 2) <= 3.40 for u in low)
    assert all(round(by[u]['max_bat'], 2) >= 3.70 or u in low for u in by)  # everyone else reads healthy


@pytest.mark.db
@pytest.mark.asyncio
async def test_reset_clears_demo_positions_and_alerts_only(scratch_pool, migrated_conn, tmp_path, monkeypatch, client):
    monkeypatch.setattr(sim, 'UPLOADS_DIR', tmp_path)
    devices = await sim.seed(migrated_conn, 6)
    from backend.routers.test import record_position
    for u, d in devices.items():
        await record_position(migrated_conn, d, 42.7, 23.3, u == 'demo_elena')
    real = await migrated_conn.fetchrow(
        "INSERT INTO devices (dev_sn, name, device_type) VALUES (1234, 'Real', 'bee') RETURNING id, NULL::uuid AS user_id")
    await record_position(migrated_conn, real, 42.7, 23.3, True)

    deleted = await sim.reset(migrated_conn)
    assert deleted == {'positions': 6, 'sos_alerts': 1}
    assert await migrated_conn.fetchval('SELECT count(*) FROM location_events') == 1      # the real device's
    assert await migrated_conn.fetchval('SELECT count(*) FROM sos_alerts') == 1
    assert await migrated_conn.fetchval("SELECT count(*) FROM users WHERE username LIKE 'demo_%'") == 6
