"""
WebSocket connection manager + PostgreSQL LISTEN/NOTIFY bridge.

The serial reader fires pg_notify on 'location_update' and 'sos_alert'.
This module listens on those channels and broadcasts JSON to all
connected browser clients.
"""

from __future__ import annotations

import asyncio
import json
import logging

import asyncpg
from fastapi import WebSocket

from .config import settings

logger = logging.getLogger(__name__)

RECONNECT_DELAY      = 5    # seconds between reconnect attempts on the LISTEN connection
HEALTHCHECK_INTERVAL = 30   # seconds between liveness pings — catches a connection that
                             # died silently (e.g. Postgres/Docker paused by system sleep)


class WSManager:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._clients.add(ws)
        logger.info('WS client connected (%d total)', len(self._clients))

    def disconnect(self, ws: WebSocket) -> None:
        self._clients.discard(ws)
        logger.info('WS client disconnected (%d total)', len(self._clients))

    async def broadcast(self, message: dict) -> None:
        dead: set[WebSocket] = set()
        for ws in self._clients:
            try:
                await ws.send_json(message)
            except Exception:
                dead.add(ws)
        self._clients -= dead

    async def listen_notifications(self) -> None:
        """Dedicated asyncpg connection that listens for pg_notify events.

        Reconnects automatically if the connection drops or goes stale (e.g. Docker/
        Postgres paused by a system sleep) instead of dying silently and requiring a
        manual backend restart to bring live updates back.
        """
        dsn = (
            f'postgresql://{settings.postgres_user}:{settings.postgres_password}'
            f'@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}'
        )

        async def _on_location(_con, _pid, _channel, payload):
            data = json.loads(payload)
            await self.broadcast({'type': 'location_update', **data})

        async def _on_sos(_con, _pid, _channel, payload):
            data = json.loads(payload)
            await self.broadcast({'type': 'sos_alert', **data})

        while True:
            conn = None
            try:
                conn = await asyncpg.connect(dsn)
                await conn.add_listener('location_update', _on_location)
                await conn.add_listener('sos_alert', _on_sos)
                logger.info('Listening for pg_notify on location_update + sos_alert')

                while True:
                    await asyncio.sleep(HEALTHCHECK_INTERVAL)
                    await conn.execute('SELECT 1')

            except asyncio.CancelledError:
                break

            except Exception as exc:
                logger.warning('pg_notify listener error (%s) — reconnecting in %ds', exc, RECONNECT_DELAY)
                await asyncio.sleep(RECONNECT_DELAY)

            finally:
                if conn and not conn.is_closed():
                    await conn.close()

        logger.info('pg_notify listener stopped')


manager = WSManager()
