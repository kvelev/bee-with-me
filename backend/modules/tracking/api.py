"""The public face of the `tracking` module: the only file other modules may import.

Every function is a thin pass-through that looks its implementation up at call time (`repository.fn(...)`, never
`from ... import fn`), on the caller's connection and without opening a transaction.
"""
from __future__ import annotations

from .domain.payload import location_update_payload
from .infrastructure import repository

__all__ = [
    'location_update_payload', 'insert_simulated_position', 'person_of', 'groups_of', 'publish_position',
    'last_fix', 'previous_sos_flag', 'insert_position', 'insert_heartbeat',
    'forget_person', 'delete_device_positions', 'delete_device_heartbeats', 'delete_positions_of_devices',
]


async def insert_simulated_position(conn, **fields):
    return await repository.insert_simulated_position(conn, **fields)


async def person_of(conn, user_id):
    return await repository.person_of(conn, user_id)


async def groups_of(conn, user_id):
    return await repository.groups_of(conn, user_id)


async def publish_position(conn, payload):
    return await repository.publish_position(conn, payload)


async def last_fix(conn, device_id):
    return await repository.last_fix(conn, device_id)


async def previous_sos_flag(conn, device_id):
    return await repository.previous_sos_flag(conn, device_id)


async def insert_position(conn, **fields):
    return await repository.insert_position(conn, **fields)


async def insert_heartbeat(conn, device_id, msg_id, battery_voltage):
    return await repository.insert_heartbeat(conn, device_id, msg_id, battery_voltage)


async def forget_person(conn, user_id):
    return await repository.forget_person(conn, user_id)


async def delete_device_positions(conn, device_id):
    return await repository.delete_device_positions(conn, device_id)


async def delete_device_heartbeats(conn, device_id):
    return await repository.delete_device_heartbeats(conn, device_id)


async def delete_positions_of_devices(conn, device_ids):
    return await repository.delete_positions_of_devices(conn, device_ids)
