"""T620: the fire clean-up (three jobs, each alone and loud) is a `fire` task."""
import logging

import pytest

pytestmark = pytest.mark.Trait("Task", "T620")


class _Acquire:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, *exc):
        return False


class _Pool:
    def acquire(self):
        return _Acquire()


@pytest.mark.Trait("Task", "T620")
@pytest.mark.asyncio
async def test_the_three_fire_jobs_run_even_when_the_first_fails(monkeypatch, caplog):
    from backend.modules.fire import tasks
    calls: list[str] = []

    async def boom(_conn, _days):
        calls.append('alerts')
        raise RuntimeError('anonymise exploded')

    async def hotspots(_conn, _days):
        calls.append('hotspots')
        return 4

    async def prune(_conn):
        calls.append('prune')
        return {'fire_hotspots': 1, 'fire_burnt_areas': 2, 'fire_suppression_zones': 3}

    monkeypatch.setattr(tasks, 'get_pool', lambda: _Pool())
    monkeypatch.setattr(tasks.repository, 'anonymise_alerts', boom)
    monkeypatch.setattr(tasks.repository, 'anonymise_hotspots', hotspots)
    monkeypatch.setattr(tasks.repository, 'prune_fire_data', prune)
    with caplog.at_level(logging.INFO):
        await tasks.cleanup_fire_data_once()
    messages = [r.getMessage() for r in caplog.records]
    assert calls == ['alerts', 'hotspots', 'prune']
    assert 'Fire alert anonymisation failed: anonymise exploded' in messages
    assert 'Fire hotspot anonymisation: anonymised 4 hotspots' in messages
    assert 'Fire data cleanup: removed 1 hotspots, 2 burnt areas, 3 disabled zones' in messages
