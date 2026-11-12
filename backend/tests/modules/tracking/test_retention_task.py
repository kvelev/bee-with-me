"""T620: the position retention is a `tracking` task started from the manifest, not a loop in `main.py`."""
import asyncio
import logging
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

REPO = Path(__file__).resolve().parents[4]

pytestmark = pytest.mark.Trait("Task", "T620")


class _Acquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *exc):
        return False


class _Pool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        return _Acquire(self.conn)


def _patch_pool(monkeypatch, conn):
    from backend.modules.tracking import tasks
    monkeypatch.setattr(tasks, 'get_pool', lambda: _Pool(conn))
    return tasks


@pytest.mark.Trait("Task", "T620")
@pytest.mark.asyncio
async def test_the_delete_statement_and_its_argument_are_todays(monkeypatch):
    from backend.config import settings
    conn = AsyncMock()
    conn.fetchval.return_value = 3
    tasks = _patch_pool(monkeypatch, conn)
    await tasks.cleanup_positions_once()
    sql, arg = conn.fetchval.call_args.args
    assert 'DELETE FROM location_events' in sql
    assert "recorded_at < NOW() - ($1 || ' days')::interval" in sql
    assert arg == str(settings.location_retention_days)


@pytest.mark.Trait("Task", "T620")
@pytest.mark.asyncio
async def test_the_pass_logs_the_count_and_the_days(monkeypatch, caplog):
    from backend.config import settings
    conn = AsyncMock()
    conn.fetchval.return_value = 7
    tasks = _patch_pool(monkeypatch, conn)
    with caplog.at_level(logging.INFO):
        await tasks.cleanup_positions_once()
    expected = 'Location cleanup: removed 7 events older than %d days' % settings.location_retention_days
    assert expected in [r.getMessage() for r in caplog.records]


@pytest.mark.Trait("Task", "T620")
@pytest.mark.asyncio
async def test_a_failed_delete_is_logged_and_does_not_raise(monkeypatch, caplog):
    conn = AsyncMock()
    conn.fetchval.side_effect = RuntimeError('db gone')
    tasks = _patch_pool(monkeypatch, conn)
    with caplog.at_level(logging.WARNING):
        await tasks.cleanup_positions_once()
    assert 'Location cleanup failed: db gone' in [r.getMessage() for r in caplog.records]


@pytest.mark.Trait("Task", "T620")
def test_the_manifest_lists_the_retention_task():
    from backend.modules.tracking import tasks
    from backend.modules.tracking.module import manifest
    assert manifest.tasks == (tasks.cleanup_positions,)


@pytest.mark.Trait("Task", "T620")
def test_main_holds_no_cleanup():
    text = (REPO / 'backend' / 'main.py').read_text(encoding='utf-8')
    for needle in ('_cleanup_old_locations', 'location_events', 'anonymise_', 'prune_fire_data', 'cleanup_task'):
        assert needle not in text, needle


@pytest.mark.Trait("Task", "T620")
@pytest.mark.asyncio
async def test_the_manifest_task_runs_its_first_pass_after_30_seconds(monkeypatch, caplog):
    from backend.core import periodic
    from backend.core.modules import start_module_tasks, stop_module_tasks
    from backend.modules.tracking.module import manifest
    conn = AsyncMock()
    conn.fetchval.return_value = 2
    _patch_pool(monkeypatch, conn)
    real_sleep = asyncio.sleep
    recorded: list[float] = []

    async def fake_sleep(seconds):
        recorded.append(seconds)
        if len(recorded) > 1:
            await asyncio.Event().wait()       # park at the second sleep (the day)
        await real_sleep(0)

    monkeypatch.setattr(periodic.asyncio, 'sleep', fake_sleep)
    with caplog.at_level(logging.INFO):
        started = start_module_tasks([manifest], lambda t, n: None)
        for _ in range(20):
            await real_sleep(0)
        await stop_module_tasks(started)
    assert recorded[0] == 30
    assert any(r.getMessage().startswith('Location cleanup: removed') for r in caplog.records)


@pytest.mark.Trait("Task", "T620")
@pytest.mark.asyncio
async def test_both_cleanups_are_started_by_the_module_list(monkeypatch):
    from backend.core import periodic
    from backend.core.modules import start_module_tasks, stop_module_tasks
    from backend.modules import MODULES
    from backend.modules.fire import tasks as fire_tasks
    from backend.modules.tracking import tasks as tracking_tasks
    jobs: list = []

    async def recorder(*args, **kwargs):
        jobs.append(args[0])
        await asyncio.Event().wait()

    monkeypatch.setattr(periodic, 'run_periodic', recorder)
    # only the two clean-ups are started; the other module tasks (feeds, alarm, reader) are left out
    only_cleanups = [type(m)(name=m.name, tasks=tuple(t for t in m.tasks if t.__name__.startswith('cleanup_')))
                     for m in MODULES if m.name in ('tracking', 'fire')]
    started = start_module_tasks(only_cleanups, lambda t, n: None)
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    await stop_module_tasks(started)
    assert len(jobs) == 2
    assert set(jobs) == {tracking_tasks.cleanup_positions_once, fire_tasks.cleanup_fire_data_once}
