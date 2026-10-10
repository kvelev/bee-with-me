"""
Fire data refresh loop: every 30 min fetch both GWIS feeds, upsert, and tell browsers.

Only one backend process refreshes at a time (session advisory lock); the others skip the cycle.
A failing feed never deletes data: the map keeps the last good copy with an honest status.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from ..database import get_pool
from . import repository
from .parse import FeedFormatError, ParseStats, parse_burnt_areas, parse_hotspots, upstream_state
from .sources import BURNT_AREAS, FEATURE_LIMIT, HOTSPOTS, FeedFetchError, FireFeedSource

logger = logging.getLogger(__name__)

REFRESH_INTERVAL_S = 30 * 60
FIRST_RUN_DELAY_S = 30
REFRESH_LOCK_KEY = 7_342_101
FEED_DEADLINE_S = 150   # overall cap per fetch; httpx's timeout is per operation, not per request
MAX_DROPPED_SHARE = 0.5   # more than this share of unusable features means the format changed

after_refresh: Callable[[], None] | None = None   # set by the alarm service (Task 15)


@dataclass
class FeedState:
    last_success_at: datetime | None = None
    last_error: str | None = None
    upstream_state: str = 'unknown'
    count: int = 0


FEEDS: dict[str, FeedState] = {'hotspots': FeedState(), 'burnt_areas': FeedState()}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _fail(name: str, exc: Exception) -> None:
    state = FEEDS[name]
    state.last_error = str(exc) or type(exc).__name__
    state.upstream_state = 'error'
    logger.warning('Fire feed %s refresh failed (%s): %s', name, type(exc).__name__, exc)


@dataclass
class _Fetched:
    rows: list
    stats: ParseStats


async def _fetch_feed(name, source, parse) -> _Fetched | None:
    """Network + parse only: needs no database connection, so none is held while GWIS answers (up to 150 s).

    Returns None (feed marked 'error', stored rows untouched) when the feed is unusable.
    """
    try:
        try:
            async with asyncio.timeout(FEED_DEADLINE_S):
                payload = await source.fetch()
        except TimeoutError:
            raise FeedFetchError('%s: no complete response within %s s (deadline)' % (name, FEED_DEADLINE_S))
        stats = ParseStats()
        rows = parse(payload, stats=stats)
        if stats.total and (not rows or stats.dropped > stats.total * MAX_DROPPED_SHARE):
            # BP-03/BP-01: an empty map after a format change must not read as "no recent detections"
            raise FeedFormatError('%s of %s features unusable %s' % (stats.dropped, stats.total, stats.dominant_reason()))
    except Exception as exc:  # noqa: BLE001 - one bad feed must not stop the other; CancelledError still propagates
        _fail(name, exc)
        return None
    return _Fetched(rows, stats)


async def _store_feed(conn, name, fetched: _Fetched, upsert, now) -> None:
    state, rows, stats = FEEDS[name], fetched.rows, fetched.stats
    try:
        async with conn.transaction():
            await upsert(conn, rows)
    except Exception as exc:  # noqa: BLE001 - see _fetch_feed
        _fail(name, exc)
        return
    state.last_success_at = now()
    state.last_error = None
    if stats.total >= FEATURE_LIMIT:
        logger.warning('Fire feed %s returned %s features (limit %s): the response is probably truncated',
                       name, stats.total, FEATURE_LIMIT)
        state.last_error = '%s features returned (limit %s): response probably truncated' % (stats.total, FEATURE_LIMIT)
    state.count = len(rows)
    state.upstream_state = upstream_state(rows, now()) if name == 'hotspots' else 'live'


async def notify_data_changed(conn) -> None:
    """Tell every browser to refetch the fire layers (also used after operator writes). No coordinates in it."""
    fetched = FEEDS['hotspots'].last_success_at
    await conn.execute("SELECT pg_notify('fire_data_updated', $1)", json.dumps({
        'fetched_at': fetched.isoformat() if fetched else None,
        'hotspot_count': FEEDS['hotspots'].count,
        'burnt_area_count': FEEDS['burnt_areas'].count,
        'upstream_state': FEEDS['hotspots'].upstream_state,
    }))


_refresh_guard = asyncio.Lock()   # one refresh at a time inside this process (the DB lock covers other processes)


async def refresh_once(pool, hotspots: FireFeedSource = HOTSPOTS, burnt_areas: FireFeedSource = BURNT_AREAS,
                       now: Callable[[], datetime] = _utcnow) -> bool:
    if _refresh_guard.locked():
        logger.info('Fire refresh skipped: a refresh is already running in this process')
        return False
    async with _refresh_guard:
        # Fetch and parse first, without a connection or the advisory lock; only the short store phase holds them.
        # The injected clock reaches the parser too, so its future-skew filter agrees with upstream_state().
        fetched_hotspots = await _fetch_feed('hotspots', hotspots,
                                             lambda payload, stats: parse_hotspots(payload, now=now(), stats=stats))
        fetched_areas = await _fetch_feed('burnt_areas', burnt_areas, parse_burnt_areas)
        async with pool.acquire() as conn:
            if not await conn.fetchval('SELECT pg_try_advisory_lock($1)', REFRESH_LOCK_KEY):
                logger.info('Fire refresh skipped: another backend process is refreshing')
                return False
            try:
                if fetched_hotspots is not None:
                    await _store_feed(conn, 'hotspots', fetched_hotspots, repository.upsert_hotspots, now)
                if fetched_areas is not None:
                    await _store_feed(conn, 'burnt_areas', fetched_areas, repository.upsert_burnt_areas, now)
                await notify_data_changed(conn)
            finally:
                await conn.execute('SELECT pg_advisory_unlock($1)', REFRESH_LOCK_KEY)
    if after_refresh is not None:
        after_refresh()
    return True


async def run() -> None:
    await asyncio.sleep(FIRST_RUN_DELAY_S)
    while True:
        try:
            await refresh_once(get_pool())
        except Exception as exc:  # noqa: BLE001 - keep the loop alive; the next cycle retries
            logger.warning('Fire refresh cycle failed: %s', exc)
        await asyncio.sleep(REFRESH_INTERVAL_S)
