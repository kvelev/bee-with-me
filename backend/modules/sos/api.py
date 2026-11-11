"""The public face of the `sos` module: the only file other modules may import.

Every function is a thin pass-through that looks its implementation up at call time (`repository.fn(...)`, never
`from ... import fn`), on the caller's connection and without opening a transaction.
"""
from __future__ import annotations

from .infrastructure import repository

__all__ = ['open_simulated_alert', 'forget_person', 'delete_device_alerts', 'delete_alerts_of_devices']


async def open_simulated_alert(conn, device_id, user_id, at):
    return await repository.open_simulated_alert(conn, device_id, user_id, at)


async def forget_person(conn, user_id):
    return await repository.forget_person(conn, user_id)


async def delete_device_alerts(conn, device_id):
    return await repository.delete_device_alerts(conn, device_id)


async def delete_alerts_of_devices(conn, device_ids):
    return await repository.delete_alerts_of_devices(conn, device_ids)
