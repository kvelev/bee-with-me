"""A job that runs shortly after start and then once a day (the retention clean-ups of `tracking` and `fire`).

A field laptop is powered down between operations, so a loop that sleeps 24 h before its first pass never runs at all.
"""
import asyncio
import logging
from typing import Awaitable, Callable

logger = logging.getLogger(__name__)


async def run_periodic(job: Callable[[], Awaitable[None]], *, first_delay: float = 30, period: float = 86_400) -> None:
    """Sleep `first_delay`, await `job()`, then sleep `period` between passes for ever.

    An exception of `job` is logged and the loop goes on; `asyncio.CancelledError` is not caught.
    """
    await asyncio.sleep(first_delay)
    while True:
        try:
            await job()
        except Exception as exc:
            logger.warning('%s failed: %s', getattr(job, '__name__', repr(job)), exc)
        await asyncio.sleep(period)
