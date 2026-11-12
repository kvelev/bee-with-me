"""B93: a module task that fails on cancellation must not leave the other tasks running and the pool open at shutdown.

T503: the fire tasks are module tasks now; the real `start_module_tasks` and `stop_module_tasks` run on a patched
`main.MODULES` with one task that fails when it is cancelled.
"""
import asyncio
import logging

import pytest

from backend import main
from backend.core.modules import ModuleManifest

pytestmark = pytest.mark.Trait("Bug", "B93")


async def _park():
    await asyncio.Event().wait()


def _quiet_startup(monkeypatch, module_task, calls):
    async def _noop():
        return None

    async def _close():
        calls.append('close_pool')

    monkeypatch.setattr(main, 'init_pool', _noop)
    monkeypatch.setattr(main, '_run_migrations', _noop)
    monkeypatch.setattr(main, '_ensure_default_admin', _noop)
    monkeypatch.setattr(main.manager, 'listen_notifications', _park)
    monkeypatch.setattr(main, 'MODULES', (ModuleManifest(name='probe', tasks=(module_task,)),))
    monkeypatch.setattr(main, 'close_pool', _close)
    import backend.hardware_reader.hid_reader as hid
    import backend.hardware_reader.reader as reader
    monkeypatch.setattr(hid, 'run', _park, raising=False)       # the real readers need a serial port / USB device
    monkeypatch.setattr(reader, 'run', _park, raising=False)


@pytest.mark.Trait("Task", "T503")
@pytest.mark.asyncio
async def test_a_module_task_failing_on_cancel_still_closes_the_pool(monkeypatch, caplog):
    calls: list[str] = []

    async def task_that_fails_on_cancel():
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            calls.append('task cancelled')
            raise RuntimeError('cleanup failed')

    _quiet_startup(monkeypatch, task_that_fails_on_cancel, calls)
    with caplog.at_level(logging.ERROR):
        async with main.lifespan(main.app):     # no exception leaves the lifespan
            await asyncio.sleep(0)       # let the task start, so the cancellation reaches its try block
    assert calls == ['task cancelled', 'close_pool']
    named = [r for r in caplog.records if r.levelno == logging.ERROR and 'probe.task_that_fails_on_cancel' in r.getMessage()]
    assert len(named) == 1


@pytest.mark.asyncio
async def test_a_cancelled_alarm_task_is_the_normal_shutdown(monkeypatch):
    calls: list[str] = []
    _quiet_startup(monkeypatch, _park, calls)
    async with main.lifespan(main.app):
        await asyncio.sleep(0)
    assert calls == ['close_pool']
