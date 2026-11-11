"""Background coroutines of the `fire` module, started by the manifest: thin wrappers, the work is in `infrastructure/`."""
from .infrastructure import poller, service


async def poll_feeds() -> None:
    # Hooks only signal re-evaluation; the single alarm actor does the work and never raises into a router/poller.
    poller.after_refresh = service.service.request_evaluation
    await poller.run()


async def alarm_loop() -> None:
    await service.service.run()
