"""Background coroutines of the `tracking` module, started by the manifest: the daily position retention."""
import logging

from ...core import periodic
from ...core.config import settings
from ...core.database import get_pool
from .infrastructure import repository

logger = logging.getLogger(__name__)


async def cleanup_positions_once() -> None:
    try:
        async with get_pool().acquire() as conn:
            deleted = await repository.delete_positions_older_than(conn, settings.location_retention_days)
            logger.info('Location cleanup: removed %d events older than %d days',
                        deleted or 0, settings.location_retention_days)
    except Exception as exc:
        logger.warning('Location cleanup failed: %s', exc)


async def cleanup_positions() -> None:
    await periodic.run_periodic(cleanup_positions_once)
