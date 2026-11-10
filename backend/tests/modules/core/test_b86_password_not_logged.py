"""B86: a database connection error must not carry the password into the log, the raised message or /ws.

Root cause: building postgresql://user:PASSWORD@host:port/db. asyncpg splits on the first '@', so a password with '@'
and a later ':' lands in the port field and the int() error repeats its tail. The connection is now made with keyword
arguments, and the text that is logged or broadcast is passed through redact().
"""

import asyncio
import logging
import sys
import traceback
from types import SimpleNamespace

import asyncpg
import pytest

from backend.core import database, ws
from backend.core.config import settings
from backend.hardware_reader import hid_reader

PW = 'ab@cd:S3CRETTAIL'
TAIL = 'S3CRETTAIL'


@pytest.fixture()
def closed_port(monkeypatch):
    monkeypatch.setattr(settings, 'postgres_password', PW)
    monkeypatch.setattr(settings, 'postgres_host', '127.0.0.1')
    monkeypatch.setattr(settings, 'postgres_port', 1)


@pytest.mark.Trait("Task", "B86")
@pytest.mark.asyncio
async def test_url_form_leaks_so_it_must_not_be_used():
    with pytest.raises(ValueError) as e:
        await asyncpg.connect(f'postgresql://u:{PW}@127.0.0.1:1/db', timeout=3)
    assert TAIL in str(e.value)   # the premise of the bug; if asyncpg stops doing this, the kwargs are merely harmless


@pytest.mark.Trait("Task", "B86")
def test_connect_kwargs_and_redact(closed_port):
    kw = database.connect_kwargs()
    assert kw['password'] == PW and kw['host'] == '127.0.0.1' and kw['port'] == 1
    assert PW not in database.redact(f'failed with {PW} here') and '***' in database.redact(f'x {PW}')


@pytest.mark.Trait("Task", "B86")
@pytest.mark.asyncio
async def test_init_pool_error_does_not_contain_password(closed_port):
    with pytest.raises(Exception) as e:
        await asyncio.wait_for(database.init_pool(), 20)
    assert TAIL not in traceback.format_exc() and TAIL not in repr(e.value)


@pytest.mark.Trait("Task", "B86")
@pytest.mark.asyncio
async def test_ws_listener_log_does_not_contain_password(closed_port, caplog, monkeypatch):
    async def stop(_delay):
        raise asyncio.CancelledError
    monkeypatch.setattr(ws.asyncio, 'sleep', stop)
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(asyncio.CancelledError):  # the reconnect sleep is where the loop is stopped
            await asyncio.wait_for(ws.WSManager().listen_notifications(), 20)
    assert any('pg_notify listener error' in r.getMessage() for r in caplog.records)
    assert TAIL not in caplog.text


@pytest.mark.Trait("Task", "B86")
@pytest.mark.asyncio
async def test_hid_reader_error_status_and_log_do_not_contain_password(closed_port, caplog, monkeypatch):
    """hid_reader's status['error'] goes out on the unauthenticated /ws: it must not carry the password."""
    sent = []

    async def broadcast():
        sent.append(dict(hid_reader.status))
        raise asyncio.CancelledError   # stop after the first failed attempt

    monkeypatch.setattr(hid_reader, '_broadcast_status', broadcast)
    monkeypatch.setattr(hid_reader, '_vid_pid', lambda: (1, 2))
    monkeypatch.setitem(sys.modules, 'hid', SimpleNamespace(device=lambda: None))
    monkeypatch.setitem(sys.modules, 'dotenv', SimpleNamespace(load_dotenv=lambda *a, **kw: None))
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(hid_reader.run(), 20)
    assert sent and sent[0]['error']
    assert TAIL not in str(sent) and TAIL not in caplog.text
