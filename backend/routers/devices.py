from typing import Annotated
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..auth import get_current_user, require_role
from ..database import get_conn

router = APIRouter(prefix='/api/devices', tags=['devices'])


class DeviceCreate(BaseModel):
    dev_sn: int
    name: str | None = None
    device_type: str = 'bee'
    user_id: UUID | None = None


class DeviceUpdate(BaseModel):
    name: str | None = None
    user_id: UUID | None = None
    is_active: bool | None = None


class AssignRequest(BaseModel):
    user_id: UUID | None   # None = detach


@router.get('/')
async def list_devices(
    conn: Annotated[asyncpg.Connection, Depends(get_conn)],
    _: Annotated[asyncpg.Record, Depends(get_current_user)],
):
    rows = await conn.fetch("""
        SELECT d.id, d.dev_sn, d.name, d.device_type, d.is_active, d.created_at,
               u.id AS user_id, u.full_name AS user_name, u.rank AS user_rank
        FROM devices d
        LEFT JOIN users u ON u.id = d.user_id
        ORDER BY d.dev_sn
    """)
    return [dict(r) for r in rows]


@router.post('/', status_code=status.HTTP_201_CREATED)
async def create_device(
    body: DeviceCreate,
    conn: Annotated[asyncpg.Connection, Depends(get_conn)],
    _: Annotated[asyncpg.Record, Depends(require_role('admin'))],
):
    try:
        row = await conn.fetchrow("""
            INSERT INTO devices (dev_sn, name, device_type, user_id)
            VALUES ($1,$2,$3,$4)
            RETURNING id, dev_sn, name, device_type
        """, body.dev_sn, body.name, body.device_type, body.user_id)
    except asyncpg.UniqueViolationError:
        raise HTTPException(status_code=409, detail='dev_sn already registered')
    return dict(row)


@router.get('/{device_id}')
async def get_device(
    device_id: UUID,
    conn: Annotated[asyncpg.Connection, Depends(get_conn)],
    _: Annotated[asyncpg.Record, Depends(get_current_user)],
):
    row = await conn.fetchrow("""
        SELECT d.*, u.full_name AS user_name, u.rank AS user_rank
        FROM devices d
        LEFT JOIN users u ON u.id = d.user_id
        WHERE d.id = $1
    """, device_id)
    if row is None:
        raise HTTPException(status_code=404, detail='Device not found')
    return dict(row)


@router.put('/{device_id}')
async def update_device(
    device_id: UUID,
    body: DeviceUpdate,
    conn: Annotated[asyncpg.Connection, Depends(get_conn)],
    _: Annotated[asyncpg.Record, Depends(require_role('admin'))],
):
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail='No fields to update')
    fields = ', '.join(f'{k} = ${i+2}' for i, k in enumerate(updates))
    row = await conn.fetchrow(
        f'UPDATE devices SET {fields} WHERE id = $1 RETURNING id, dev_sn, name, is_active',
        device_id, *updates.values(),
    )
    if row is None:
        raise HTTPException(status_code=404, detail='Device not found')
    return dict(row)


@router.put('/{device_id}/assign')
async def assign_device(
    device_id: UUID,
    body: AssignRequest,
    conn: Annotated[asyncpg.Connection, Depends(get_conn)],
    _: Annotated[asyncpg.Record, Depends(require_role('admin'))],
):
    await conn.execute('UPDATE devices SET user_id = $1 WHERE id = $2', body.user_id, device_id)
    return {'device_id': str(device_id), 'user_id': str(body.user_id) if body.user_id else None}


@router.delete('/{device_id}', status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_device(
    device_id: UUID,
    conn: Annotated[asyncpg.Connection, Depends(get_conn)],
    _: Annotated[asyncpg.Record, Depends(require_role('admin'))],
):
    await conn.execute('UPDATE devices SET is_active = FALSE WHERE id = $1', device_id)


@router.post('/{device_id}/reactivate', status_code=status.HTTP_204_NO_CONTENT)
async def reactivate_device(
    device_id: UUID,
    conn: Annotated[asyncpg.Connection, Depends(get_conn)],
    _: Annotated[asyncpg.Record, Depends(require_role('admin'))],
):
    await conn.execute('UPDATE devices SET is_active = TRUE WHERE id = $1', device_id)


@router.delete('/{device_id}/permanent', status_code=status.HTTP_204_NO_CONTENT)
async def delete_device_permanent(
    device_id: UUID,
    conn: Annotated[asyncpg.Connection, Depends(get_conn)],
    _: Annotated[asyncpg.Record, Depends(require_role('admin'))],
):
    async with conn.transaction():
        await conn.execute('DELETE FROM sos_alerts       WHERE device_id = $1', device_id)
        await conn.execute('DELETE FROM location_events  WHERE device_id = $1', device_id)
        await conn.execute('DELETE FROM repeater_events  WHERE device_id = $1', device_id)
        deleted = await conn.fetchval(
            'DELETE FROM devices WHERE id = $1 RETURNING id', device_id
        )
    if deleted is None:
        raise HTTPException(status_code=404, detail='Device not found')
