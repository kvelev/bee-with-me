"""The public face of the `fire` module: the only file other modules may import.

Every function is a thin pass-through that looks its implementation up at call time (`repository.fn(...)`, never
`from ... import fn`), so a test that replaces the function on the infrastructure module is seen by every caller.
"""
from __future__ import annotations

from .infrastructure import repository, service

ALARM_LOCK_KEY = repository.ALARM_LOCK_KEY


def request_evaluation() -> None:
    service.service.request_evaluation()


async def resolve_hq_alerts(*args, **kwargs):
    return await repository.resolve_hq_alerts(*args, **kwargs)


async def resolve_disabled_alerts(*args, **kwargs):
    return await repository.resolve_disabled_alerts(*args, **kwargs)


async def get_alert_out(*args, **kwargs):
    return await repository.get_alert_out(*args, **kwargs)


async def notify(conn, channel, payload):
    return await service.notify(conn, channel, payload)


async def notify_alerts_updated(conn, alert_ids):
    return await service.notify_alerts_updated(conn, alert_ids)


async def lock_and_resolve_device_alerts(conn, device_id, actor_id):
    return await repository.lock_and_resolve_device_alerts(conn, device_id, actor_id)


async def anonymise_alerts(*args, **kwargs):
    return await repository.anonymise_alerts(*args, **kwargs)


async def anonymise_hotspots(*args, **kwargs):
    return await repository.anonymise_hotspots(*args, **kwargs)


async def prune_fire_data(*args, **kwargs):
    return await repository.prune_fire_data(*args, **kwargs)
