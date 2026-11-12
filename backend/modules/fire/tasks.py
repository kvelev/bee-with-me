"""Background coroutines of the `fire` module, started by the manifest: thin wrappers, the work is in `infrastructure/`."""
import logging

from ...core import periodic
from ...core.config import settings
from ...core.database import get_pool
from .infrastructure import poller, repository, service

logger = logging.getLogger(__name__)


async def poll_feeds() -> None:
    # Hooks only signal re-evaluation; the single alarm actor does the work and never raises into a router/poller.
    poller.after_refresh = service.service.request_evaluation
    await poller.run()


async def alarm_loop() -> None:
    await service.service.run()


async def cleanup_fire_data_once() -> None:
    """Retention of the fire data (DP-03): each job has its own connection and `try`, so one failure never stops the next."""
    try:
        async with get_pool().acquire() as conn:
            anonymised = await repository.anonymise_alerts(conn, settings.location_retention_days)
            logger.info('Fire alert anonymisation: anonymised %d resolved alerts', anonymised)
    except Exception as exc:
        logger.warning('Fire alert anonymisation failed: %s', exc)
    try:
        async with get_pool().acquire() as conn:
            anonymised = await repository.anonymise_hotspots(conn, settings.location_retention_days)
            logger.info('Fire hotspot anonymisation: anonymised %d hotspots', anonymised or 0)
    except Exception as exc:
        logger.warning('Fire hotspot anonymisation failed: %s', exc)
    try:
        async with get_pool().acquire() as conn:
            pruned = await repository.prune_fire_data(conn)
            logger.info('Fire data cleanup: removed %d hotspots, %d burnt areas, %d disabled zones',
                        pruned['fire_hotspots'], pruned['fire_burnt_areas'], pruned['fire_suppression_zones'])
    except Exception as exc:
        logger.warning('Fire data prune failed: %s', exc)


async def cleanup_fire_data() -> None:
    await periodic.run_periodic(cleanup_fire_data_once)
