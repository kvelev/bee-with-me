"""Characterisation of the live channel: ws.WSManager, the pg_notify listener loop and routers/ws.py.

_forward is covered by test_ws_forward.py and not repeated here.
"""

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import ws
from backend.routers import ws as ws_router

pytestmark = [pytest.mark.Trait("Task", "T116")]


class _Client:
    def __init__(self, fail=False):
        self.sent = []
        self.fail = fail

    async def send_json(self, message):
        if self.fail:
            raise RuntimeError('socket closed')
        self.sent.append(message)


def test_ws_endpoint_registers_and_unregisters_the_client():
    app = FastAPI()
    app.include_router(ws_router.router)
    assert len(ws.manager._clients) == 0
    with TestClient(app) as tc:
        with tc.websocket_connect('/ws') as sock:
            sock.send_text('ping')
            assert len(ws.manager._clients) == 1
        assert len(ws.manager._clients) == 0


@pytest.mark.asyncio
async def test_broadcast_drops_a_dead_client_and_still_reaches_the_others():
    manager = ws.WSManager()
    dead, alive = _Client(fail=True), _Client()
    manager._clients.add(dead)
    manager._clients.add(alive)
    await manager.broadcast({'type': 'sos_alert', 'dev_sn': 7})
    assert alive.sent == [{'type': 'sos_alert', 'dev_sn': 7}]
    assert manager._clients == {alive}


@pytest.mark.asyncio
async def test_listener_reconnects_after_a_connect_error(monkeypatch, caplog):
    attempts = []

    async def fake_connect(dsn):
        attempts.append(dsn)
        if len(attempts) == 1:
            raise OSError('db down')
        raise asyncio.CancelledError()

    delays = []

    async def fake_sleep(delay):
        delays.append(delay)

    monkeypatch.setattr(ws.asyncpg, 'connect', fake_connect)
    monkeypatch.setattr(ws.asyncio, 'sleep', fake_sleep)
    with caplog.at_level('WARNING'):
        await ws.WSManager().listen_notifications()
    assert len(attempts) == 2
    assert delays == [ws.RECONNECT_DELAY]
    warnings = [r for r in caplog.records if r.levelname == 'WARNING']
    assert len(warnings) == 1 and 'reconnecting' in warnings[0].getMessage()


@pytest.mark.asyncio
async def test_listener_listens_on_every_forwarded_channel(monkeypatch):
    class FakeConn:
        def __init__(self):
            self.channels = []
            self.closed = False

        async def add_listener(self, channel, callback):
            self.channels.append(channel)

        async def execute(self, sql):
            return None

        def is_closed(self):
            return self.closed

        async def close(self):
            self.closed = True

    conn = FakeConn()

    async def fake_connect(dsn):
        return conn

    async def fake_sleep(delay):
        assert delay == ws.HEALTHCHECK_INTERVAL
        raise asyncio.CancelledError()

    monkeypatch.setattr(ws.asyncpg, 'connect', fake_connect)
    monkeypatch.setattr(ws.asyncio, 'sleep', fake_sleep)
    await ws.WSManager().listen_notifications()
    assert set(conn.channels) == set(ws.FORWARDED_CHANNELS)
    assert len(conn.channels) == len(ws.FORWARDED_CHANNELS)
    assert conn.closed is True
