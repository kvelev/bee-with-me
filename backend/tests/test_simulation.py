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


@pytest.mark.parametrize('body', [{'interval': 0.1}, {'interval': 600}, {'lat': 91}, {'lon': -181}])
def test_start_rejects_out_of_range_input(client, body):
    assert client.post('/api/test/simulation/start', json=body).status_code == 422


# ── On a real database ────────────────────────────────────────────────────────

@pytest.mark.db
@pytest.mark.asyncio
async def test_seed_is_idempotent_and_copies_photos(migrated_conn, tmp_path, monkeypatch):
    monkeypatch.setattr(sim, 'UPLOADS_DIR', tmp_path)
    first = await sim.seed(migrated_conn)
    second = await sim.seed(migrated_conn)
    assert len(first) == len(sim.DEMO_USERS)
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
