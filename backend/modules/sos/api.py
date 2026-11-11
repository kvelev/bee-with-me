"""The public face of the `sos` module: the only file other modules may import.

Every function is a thin pass-through that looks its implementation up at call time (`repository.fn(...)`, never
`from ... import fn`), on the caller's connection and without opening a transaction.
"""
from __future__ import annotations

from ...core.config import settings
from .infrastructure import repository

__all__ = ['has_open_alert', 'raise_sos', 'open_simulated_alert', 'forget_person', 'delete_device_alerts', 'delete_alerts_of_devices']


async def open_simulated_alert(conn, device_id, user_id, at):
    return await repository.open_simulated_alert(conn, device_id, user_id, at)


async def forget_person(conn, user_id):
    return await repository.forget_person(conn, user_id)


async def delete_device_alerts(conn, device_id):
    return await repository.delete_device_alerts(conn, device_id)


async def delete_alerts_of_devices(conn, device_ids):
    return await repository.delete_alerts_of_devices(conn, device_ids)


async def has_open_alert(conn, device_id):
    return await repository.has_open_alert(conn, device_id)


async def raise_sos(conn, *, device_id, user_id, dev_sn, triggered_at):
    return await repository.raise_sos(conn, device_id=device_id, user_id=user_id, dev_sn=dev_sn,
                                      triggered_at=triggered_at, with_person=settings.live_personal_fields)
