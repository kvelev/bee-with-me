"""T503: `fire.api` is the only door into the fire module; the callers use it and the fire tasks come from the manifest."""
import ast
import asyncio
import inspect
import logging
import subprocess
import sys
import uuid
from pathlib import Path

import asyncpg
import pytest

from backend.modules.fire import api
from backend.modules.fire.infrastructure import poller, repository, service
from backend.modules.fire.module import manifest
from backend.routers import devices
from backend.tests.architecture import rules

REPO = Path(__file__).resolve().parents[4]

pytestmark = pytest.mark.Trait("Task", "T503")


@pytest.mark.Trait("Task", "T503")
def test_the_device_delete_broadcast_still_goes_through_the_names_of_devices():
    source = inspect.getsource(devices.delete_device_permanent)
    assert 'fire_notify(' in source and 'fire_repository.get_alert_out(' in source
    assert hasattr(devices, 'fire_notify')


@pytest.mark.Trait("Task", "T503")
def test_the_alarm_lock_key_is_one_value():
    from backend.fire.service import ALARM_LOCK_KEY as old_path_key
    assert repository.ALARM_LOCK_KEY == service.ALARM_LOCK_KEY == api.ALARM_LOCK_KEY == old_path_key
    done = subprocess.run([sys.executable, '-c', 'import backend.modules.fire.infrastructure.repository'],
                          cwd=REPO, capture_output=True, text=True)
    assert done.returncode == 0, done.stderr


PASS_THROUGH = [
    ('resolve_hq_alerts', repository), ('resolve_disabled_alerts', repository), ('get_alert_out', repository),
    ('notify', service), ('notify_alerts_updated', service),
    ('anonymise_alerts', repository), ('anonymise_hotspots', repository), ('prune_fire_data', repository),
]


@pytest.mark.Trait("Task", "T503")
@pytest.mark.asyncio
@pytest.mark.parametrize('name,owner', PASS_THROUGH)
async def test_api_looks_the_implementation_up_at_call_time(monkeypatch, name, owner):
    seen = []

    async def fake(*args, **kwargs):
        seen.append((args, kwargs))
        return 'marker'

    args = ('a', 2) if name == 'notify_alerts_updated' else ('a', 2, 'c')   # notify_alerts_updated(conn, alert_ids)
    monkeypatch.setattr(owner, name, fake)
    assert await getattr(api, name)(*args) == 'marker'
    assert seen == [(args, {})]


@pytest.mark.Trait("Task", "T503")
def test_request_evaluation_reaches_the_service_instance(monkeypatch):
    calls = []
    monkeypatch.setattr(service.service, 'request_evaluation', lambda: calls.append(1))
    api.request_evaluation()
    assert calls == [1]


@pytest.mark.Trait("Task", "T503")
@pytest.mark.asyncio
async def test_lock_and_resolve_looks_up_at_call_time(monkeypatch):
    async def fake(conn, device_id, actor_id):
        return [('row', conn, device_id, actor_id)]

    monkeypatch.setattr(repository, 'lock_and_resolve_device_alerts', fake)
    assert await api.lock_and_resolve_device_alerts('c', 'd', 'u') == [('row', 'c', 'd', 'u')]


def _record(mock_conn, lock_error=None):
    calls = []

    async def execute(sql, *args):
        calls.append(sql)
        if lock_error and 'pg_advisory_xact_lock' in sql:
            raise lock_error

    async def fetch(sql, *args):
        calls.append(sql)
        return []

    async def fetchval(sql, *args):
        calls.append(sql)
        return uuid.uuid4()

    mock_conn.execute, mock_conn.fetch, mock_conn.fetchval = execute, fetch, fetchval
    return calls


ORDER = ['FROM sos_alerts', 'FROM location_events', 'FROM repeater_events',
         'SET LOCAL lock_timeout', 'pg_advisory_xact_lock', 'UPDATE fire_alerts', 'FROM devices']


@pytest.mark.Trait("Task", "T503")
def test_device_delete_keeps_the_statement_order(client, mock_conn):
    calls = _record(mock_conn)
    assert client.delete(f'/api/devices/{uuid.uuid4()}/permanent').status_code == 204
    positions = [next(i for i, sql in enumerate(calls) if needle in sql) for needle in ORDER]
    assert positions == sorted(positions) and len(calls) == len(ORDER)
    mock_conn.transaction.assert_called_once()


@pytest.mark.Trait("Task", "T503")
def test_a_busy_alarm_lock_still_answers_503(client, mock_conn):
    _record(mock_conn, lock_error=asyncpg.exceptions.LockNotAvailableError('busy'))
    resp = client.delete(f'/api/devices/{uuid.uuid4()}/permanent')
    assert resp.status_code == 503
    assert resp.json()['detail'] == 'The fire alarm is busy evaluating; nothing was deleted, try again in a moment'


@pytest.mark.Trait("Task", "T503")
def test_fire_tasks_are_in_the_manifest():
    assert [t.__name__ for t in manifest.tasks] == ['poll_feeds', 'alarm_loop']
    assert rules.check_manifest_wiring([manifest], REPO / 'backend') == []


@pytest.mark.Trait("Task", "T503")
@pytest.mark.asyncio
async def test_poll_feeds_wires_the_alarm_before_the_first_refresh(monkeypatch):
    seen = []

    async def run():
        seen.append(poller.after_refresh)

    monkeypatch.setattr(poller, 'run', run)
    monkeypatch.setattr(poller, 'after_refresh', None)
    from backend.modules.fire import tasks
    await tasks.poll_feeds()
    assert len(seen) == 1 and seen[0] == service.service.request_evaluation


async def _park():
    await asyncio.Event().wait()


def _quiet_startup(monkeypatch, main, calls):
    async def _noop():
        return None

    async def _close():
        calls.append('close_pool')

    monkeypatch.setattr(main, 'init_pool', _noop)
    monkeypatch.setattr(main, '_run_migrations', _noop)
    monkeypatch.setattr(main, '_ensure_default_admin', _noop)
    monkeypatch.setattr(main, '_cleanup_old_locations', _park)
    monkeypatch.setattr(main.manager, 'listen_notifications', _park)
    monkeypatch.setattr(main, 'close_pool', _close)
    import backend.hardware_reader.hid_reader as hid
    import backend.hardware_reader.reader as reader
    monkeypatch.setattr(hid, 'run', _park, raising=False)
    monkeypatch.setattr(reader, 'run', _park, raising=False)


@pytest.mark.Trait("Task", "T503")
@pytest.mark.asyncio
async def test_fire_tasks_are_stopped_before_the_pool_closes(monkeypatch):
    from backend import main
    calls: list[str] = []

    def recording(label):
        async def run():
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                calls.append(f'{label} cancelled')
                raise
        return run

    _quiet_startup(monkeypatch, main, calls)
    monkeypatch.setattr(poller, 'run', recording('poller'))
    monkeypatch.setattr(service.service, 'run', recording('alarm'))
    async with main.lifespan(main.app):
        await asyncio.sleep(0)
        await asyncio.sleep(0)
    assert calls.index('close_pool') == len(calls) - 1
    assert {'poller cancelled', 'alarm cancelled'} <= set(calls[:-1])


@pytest.mark.Trait("Task", "T503")
@pytest.mark.asyncio
async def test_a_crashed_fire_task_is_logged_by_name(monkeypatch, caplog):
    from backend import main
    calls: list[str] = []

    async def crash():
        raise RuntimeError('x')

    _quiet_startup(monkeypatch, main, calls)
    monkeypatch.setattr(poller, 'run', _park)
    monkeypatch.setattr(service.service, 'run', crash)
    with caplog.at_level(logging.ERROR):
        async with main.lifespan(main.app):
            await asyncio.sleep(0)
            await asyncio.sleep(0)
    errors = [r for r in caplog.records if r.levelno == logging.ERROR and 'fire.alarm_loop' in r.getMessage()]
    assert len(errors) == 1


@pytest.mark.Trait("Task", "T503")
def test_main_names_no_fire_internals():
    tree = ast.parse((REPO / 'backend' / 'main.py').read_text(encoding='utf-8'))
    from_fire_api = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ''
            assert mod != 'fire' and mod != 'routers.fire' and not mod.startswith('fire.'), mod
            if mod == 'routers':
                assert 'fire' not in [a.name for a in node.names]
            if mod == 'modules.fire.api':
                from_fire_api += 1
        if isinstance(node, ast.Name):
            assert node.id not in ('fire_poller', 'fire_alarm')
        if isinstance(node, ast.alias):
            assert (node.asname or node.name) not in ('fire_poller', 'fire_alarm')
    assert from_fire_api == 1


@pytest.mark.Trait("Task", "T503")
def test_no_production_file_imports_the_old_fire_package():
    grimp = pytest.importorskip('grimp')
    sys.path.insert(0, str(REPO))
    try:
        graph = grimp.build_graph('backend', include_external_packages=False)
    finally:
        sys.path.remove(str(REPO))
    offenders = []
    for module in graph.modules:
        if module == 'backend.fire' or module.startswith('backend.fire.'):
            continue
        for imported in graph.find_modules_directly_imported_by(module):
            if imported == 'backend.fire' or imported.startswith('backend.fire.'):
                offenders.append((module, imported))
    assert offenders == []
