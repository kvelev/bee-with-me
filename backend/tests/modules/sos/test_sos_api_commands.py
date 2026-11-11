"""T541: `sos.api` opens simulated alerts and clears person and device references."""
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.modules.sos import api
from backend.modules.sos.infrastructure import repository
from backend.tests.architecture import sql_scan

REPO = Path(__file__).resolve().parents[4]

pytestmark = pytest.mark.Trait("Task", "T541")


def _conn():
    conn = MagicMock()
    conn.transaction = MagicMock()
    conn.execute = AsyncMock(return_value='DELETE 3')
    conn.fetchval = AsyncMock(return_value=3)
    return conn


@pytest.mark.Trait("Task", "T541")
@pytest.mark.asyncio
async def test_forget_person_clears_user_id_then_resolved_by():
    conn, uid = _conn(), uuid.uuid4()
    await api.forget_person(conn, uid)
    sqls = [c.args[0] for c in conn.execute.await_args_list]
    assert len(sqls) == 2
    assert 'SET user_id = NULL' in sqls[0] and 'SET resolved_by = NULL' in sqls[1]
    assert all(c.args[1:] == (uid,) for c in conn.execute.await_args_list)
    conn.transaction.assert_not_called()


@pytest.mark.Trait("Task", "T541")
@pytest.mark.asyncio
async def test_a_simulated_alert_is_not_opened_twice():
    conn, did, uid = _conn(), uuid.uuid4(), uuid.uuid4()
    at = datetime(2026, 11, 1, tzinfo=timezone.utc)
    await api.open_simulated_alert(conn, did, uid, at)
    sql, *args = conn.execute.await_args.args
    assert 'WHERE NOT EXISTS' in sql and 'INSERT INTO sos_alerts' in sql
    assert args == [did, uid, at]
    conn.transaction.assert_not_called()


@pytest.mark.Trait("Task", "T541")
@pytest.mark.asyncio
async def test_delete_commands_run_on_the_callers_connection():
    conn, did = _conn(), uuid.uuid4()
    await api.delete_device_alerts(conn, did)
    assert await api.delete_alerts_of_devices(conn, [did]) == 3
    conn.transaction.assert_not_called()


@pytest.mark.Trait("Task", "T541")
@pytest.mark.asyncio
@pytest.mark.parametrize('name,args', [
    ('open_simulated_alert', ('d', 'u', 'a')), ('forget_person', ('u',)),
    ('delete_device_alerts', ('d',)), ('delete_alerts_of_devices', (['d'],))])
async def test_api_looks_the_implementation_up_at_call_time(monkeypatch, name, args):
    seen = []

    async def fake(*a, **k):
        seen.append((a, k))
        return 'marker'

    monkeypatch.setattr(repository, name, fake)
    assert await getattr(api, name)('conn', *args) == 'marker'
    assert seen == [(('conn', *args), {})]


@pytest.mark.Trait("Task", "T541")
def test_no_writer_outside_the_modules_is_left():
    allowed = ('modules/sos/infrastructure/repository.py', 'hardware_reader/reader.py', 'main.py')
    stray = {(str(p).replace('\\', '/'), t, v) for p, t, v in sql_scan.scan_writes(REPO / 'backend')
             if t == 'sos_alerts' and not str(p).replace('\\', '/').endswith(allowed)}
    assert not stray, stray
