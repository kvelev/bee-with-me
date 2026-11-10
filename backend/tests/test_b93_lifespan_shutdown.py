"""B93: a failing alarm task must not leave module tasks running and the pool open at shutdown."""
import asyncio

import pytest

from backend import main

pytestmark = pytest.mark.Trait("Bug", "B93")


async def _park():
    await asyncio.Event().wait()


def _quiet_startup(monkeypatch, alarm_run, calls):
    async def _noop():
        return None

    async def _stop(tasks):
        calls.append('stop_module_tasks')

    async def _close():
        calls.append('close_pool')

    monkeypatch.setattr(main, 'init_pool', _noop)
    monkeypatch.setattr(main, '_run_migrations', _noop)
    monkeypatch.setattr(main, '_ensure_default_admin', _noop)
    monkeypatch.setattr(main, '_cleanup_old_locations', _park)
    monkeypatch.setattr(main.manager, 'listen_notifications', _park)
    monkeypatch.setattr(main.fire_poller, 'run', _park)
    monkeypatch.setattr(main.fire_alarm, 'run', alarm_run)
    monkeypatch.setattr(main, 'start_module_tasks', lambda modules, on_done: [])
    monkeypatch.setattr(main, 'stop_module_tasks', _stop)
    monkeypatch.setattr(main, 'close_pool', _close)
    import backend.hardware_reader.hid_reader as hid
    import backend.hardware_reader.reader as reader
    monkeypatch.setattr(hid, 'run', _park, raising=False)       # the real readers need a serial port / USB device
    monkeypatch.setattr(reader, 'run', _park, raising=False)


@pytest.mark.asyncio
async def test_a_failing_alarm_task_still_stops_module_tasks_and_closes_the_pool(monkeypatch):
    calls: list[str] = []

    async def alarm_that_fails_on_cancel():
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            raise RuntimeError('cleanup failed')

    _quiet_startup(monkeypatch, alarm_that_fails_on_cancel, calls)
    with pytest.raises(RuntimeError, match='cleanup failed'):
        async with main.lifespan(main.app):
            await asyncio.sleep(0)       # let the alarm task start, so the cancellation reaches its try block
    assert calls == ['stop_module_tasks', 'close_pool']


@pytest.mark.asyncio
async def test_a_cancelled_alarm_task_is_the_normal_shutdown(monkeypatch):
    calls: list[str] = []
    _quiet_startup(monkeypatch, _park, calls)
    async with main.lifespan(main.app):
        await asyncio.sleep(0)
    assert calls == ['stop_module_tasks', 'close_pool']
