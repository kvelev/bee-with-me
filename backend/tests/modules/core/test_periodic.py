"""T620: `core.periodic.run_periodic` is the daily loop that `main.py` used to hold for the clean-up."""
import asyncio
import logging

import pytest

pytestmark = pytest.mark.Trait("Task", "T620")


def _fake_sleep(monkeypatch, sleeps, stop_after):
    from backend.core import periodic

    async def fake_sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) > stop_after:
            raise asyncio.CancelledError

    monkeypatch.setattr(periodic.asyncio, 'sleep', fake_sleep)


@pytest.mark.Trait("Task", "T620")
@pytest.mark.asyncio
async def test_the_first_pass_runs_after_30_seconds_and_the_next_after_a_day(monkeypatch):
    from backend.core import periodic
    sleeps: list[float] = []
    passes: list[int] = []

    async def job():
        passes.append(len(sleeps))

    _fake_sleep(monkeypatch, sleeps, stop_after=2)
    with pytest.raises(asyncio.CancelledError):
        await periodic.run_periodic(job)
    assert sleeps[:2] == [30, 86_400]
    assert passes == [1, 2]


@pytest.mark.Trait("Task", "T620")
@pytest.mark.asyncio
async def test_a_failing_job_is_logged_and_the_loop_goes_on(monkeypatch, caplog):
    from backend.core import periodic
    sleeps: list[float] = []
    runs: list[int] = []

    async def flaky_job():
        runs.append(1)
        raise RuntimeError('boom')

    _fake_sleep(monkeypatch, sleeps, stop_after=2)
    with caplog.at_level(logging.WARNING), pytest.raises(asyncio.CancelledError):
        await periodic.run_periodic(flaky_job)
    assert len(runs) == 2
    assert [r.getMessage() for r in caplog.records].count('flaky_job failed: boom') == 2


@pytest.mark.Trait("Task", "T620")
@pytest.mark.asyncio
async def test_cancelling_stops_the_loop():
    from backend.core import periodic

    async def job():
        return None

    task = asyncio.create_task(periodic.run_periodic(job))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert task.cancelled()
