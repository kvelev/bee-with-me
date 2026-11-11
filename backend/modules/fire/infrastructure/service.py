"""
FireAlarmService: the single actor that owns every alarm write.

Routers and the poller never evaluate; they call request_evaluation(). One loop wakes on that event
or every 60 s, evaluates, then sends repeats. Within a process this serialises all alarm writes;
across processes a transaction-scoped advisory lock lets only one tick run at a time. Alert writes
and their pg_notify share one transaction, so a rolled-back alert never reaches a browser.

Failure policy (BP-03, TP-02): a tick that fails is logged at ERROR and the loop carries on; it never
touches the tracking path. If the settings cannot be read the tick is skipped, because evaluating
with "no HQ and no targets" would look like a mass all-clear.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Callable

import asyncpg

from ....core.database import get_pool
from . import repository as repo
from ..domain.proximity import TARGET_POSITION_MAX_AGE_MIN, evaluate

logger = logging.getLogger(__name__)

ALARM_LOCK_KEY = repo.ALARM_LOCK_KEY
TICK_S = 60
REPEAT_IDS_PER_MESSAGE = 100


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def notify(conn: asyncpg.Connection, channel: str, payload: dict) -> None:
    await conn.execute('SELECT pg_notify($1, $2)', channel, json.dumps(payload, default=str))


async def notify_alerts_updated(conn: asyncpg.Connection, alert_ids) -> None:
    """Broadcast fire_alert_updated for already-committed changes. Best effort per alert: the change is durable, a
    failed broadcast must not turn the caller's successful request into an error."""
    for alert_id in alert_ids:
        try:
            out = await repo.get_alert_out(conn, alert_id)
            if out is not None:
                await notify(conn, 'fire_alert_updated', out.model_dump(mode='json'))
        except Exception:  # noqa: BLE001
            logger.warning('fire alert %s resolved but its update was not broadcast', alert_id, exc_info=True)


class FireAlarmService:
    def __init__(self, pool_getter: Callable = get_pool, now: Callable[[], datetime] = _utcnow,
                 tick_s: float = TICK_S):
        self._pool_getter = pool_getter
        self._now = now
        self._tick_s = tick_s
        self._wake = asyncio.Event()
        self._hq_missing_logged = False

    def request_evaluation(self) -> None:
        """Signal only; safe to hand to the poller and the settings router (never raises)."""
        try:
            self._wake.set()
        except Exception as exc:  # noqa: BLE001 - a hook must not break its caller
            logger.error('Fire alarm: could not request an evaluation: %s', exc)

    async def run(self) -> None:
        self._wake.set()   # evaluate right after start-up, not only after the first interval
        while True:
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=self._tick_s)
            except asyncio.TimeoutError:
                pass
            self._wake.clear()
            try:
                await self.tick()
            except Exception as exc:  # noqa: BLE001 - the alarm loop must survive a bad tick
                logger.error('Fire alarm tick failed: %s', exc, exc_info=True)

    async def tick(self) -> bool:
        """One evaluation + repeat pass. False when skipped (lock held elsewhere or settings unreadable)."""
        async with self._pool_getter().acquire() as conn:
            async with conn.transaction():
                if not await conn.fetchval('SELECT pg_try_advisory_xact_lock($1)', ALARM_LOCK_KEY):
                    return False
                try:
                    settings, hq = await repo.load_alarm_settings(conn)
                except Exception as exc:  # noqa: BLE001 - never evaluate on a failed read (would mask or mass-resolve)
                    logger.error('Fire alarm tick skipped: settings could not be read: %s', exc)
                    return False
                # Each step runs in its own savepoint inside the lock-holding transaction: a failure rolls
                # back only that step (and its pending notifications), the other step still runs, the
                # advisory lock stays held, and notifications are delivered only when the outer commit lands.
                try:
                    async with conn.transaction():
                        await self._evaluate(conn, settings, hq)
                except Exception as exc:  # noqa: BLE001 - repeats of open alerts must not depend on evaluation
                    logger.error('Fire alarm evaluation failed: %s', exc, exc_info=True)
                try:
                    async with conn.transaction():
                        await self._repeat(conn)
                except Exception as exc:  # noqa: BLE001 - a failed repeat must not undo the evaluation
                    logger.error('Fire alarm repeat step failed: %s', exc, exc_info=True)
        return True

    async def _evaluate(self, conn: asyncpg.Connection, settings, hq) -> None:
        targets = ([hq] if hq else []) + await repo.load_rescuer_targets(conn, TARGET_POSITION_MAX_AGE_MIN)
        decisions = evaluate(
            await repo.load_evaluation_hotspots(conn, settings.alarm_max_age_hours),
            targets,
            await repo.load_active_zones(conn),
            await repo.load_open_alerts(conn),
            settings,
            self._now(),
        )
        if decisions.hq_missing:
            if not self._hq_missing_logged:   # once per state change, not every tick
                logger.warning('HQ alert kept open: HQ position missing')
            self._hq_missing_logged = True
        else:
            self._hq_missing_logged = False

        await repo.set_suppression(conn, decisions.suppressed)
        for alert_id, reason in decisions.to_resolve:
            if await repo.resolve_alert(conn, alert_id, reason):
                out = await repo.get_alert_out(conn, alert_id)
                if out is not None:
                    await notify(conn, 'fire_alert_updated', out.model_dump(mode='json'))
        # A deactivated device or user can no longer report: its open rescuer alerts end as 'disabled' (no actor),
        # whichever way it was deactivated. Missing data of an ACTIVE rescuer is not covered here (B40).
        for alert_id in await repo.resolve_disabled_alerts(conn):
            out = await repo.get_alert_out(conn, alert_id)
            if out is not None:
                await notify(conn, 'fire_alert_updated', out.model_dump(mode='json'))
        for new in decisions.to_open:
            alert_id = await repo.insert_alert(conn, new)
            if alert_id:
                out = await repo.get_alert_out(conn, alert_id)
                logger.warning('Fire alert: hotspot %s within %d m of %s %s',
                               new.hotspot_id, new.distance_m, new.target_type, new.device_id or 'HQ')
                if out is not None:
                    await notify(conn, 'fire_alert', out.model_dump(mode='json'))

    async def _repeat(self, conn: asyncpg.Connection) -> None:
        ids = await repo.mark_repeats_due(conn)
        for start in range(0, len(ids), REPEAT_IDS_PER_MESSAGE):
            await notify(conn, 'fire_alert_repeat', {'alert_ids': ids[start:start + REPEAT_IDS_PER_MESSAGE]})


service = FireAlarmService()
