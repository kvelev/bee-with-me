"""
WebSocket connection manager + PostgreSQL LISTEN/NOTIFY bridge.

The hardware reader and the fire feature fire pg_notify on the channels in FORWARDED_CHANNELS; this module forwards each one to every connected browser as {'type': <channel>, ...payload}.
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

FORWARDED_CHANNELS = (
    'location_update', 'sos_alert',
    'fire_data_updated', 'fire_alert', 'fire_alert_repeat', 'fire_alert_updated', 'fire_zones_updated',
)


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

    async def _forward(self, _con, _pid, channel: str, payload: str) -> None:
        try:
            data = json.loads(payload)
        except ValueError:
            data = None
        if not isinstance(data, dict):
            logger.warning('Dropped a non-object notification on channel %s', channel)
            return
        await self.broadcast({**data, 'type': channel})   # the channel wins: a payload key cannot spoof the type

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

        while True:
            conn = None
            try:
                conn = await asyncpg.connect(dsn)
                for channel in FORWARDED_CHANNELS:
                    await conn.add_listener(channel, self._forward)
                logger.info('Listening for pg_notify on %s', ', '.join(FORWARDED_CHANNELS))

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
