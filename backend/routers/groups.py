from typing import Annotated
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from ..auth import get_current_user, require_role
from ..database import get_conn

router = APIRouter(prefix='/api/groups', tags=['groups'])


class GroupCreate(BaseModel):
    name: str
    description: str | None = None
    organization: str | None = None
    color: str = '#3388ff'


class GroupUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    organization: str | None = None
    color: str | None = None
    is_active: bool | None = None


class MemberAdd(BaseModel):
    user_id: UUID
    is_leader: bool = False


@router.get('/')
async def list_groups(
    conn: Annotated[asyncpg.Connection, Depends(get_conn)],
    _: Annotated[asyncpg.Record, Depends(get_current_user)],
    include_members: bool = Query(False),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    total = await conn.fetchval('SELECT COUNT(*) FROM groups')
    if include_members:
        rows = await conn.fetch("""
            SELECT g.id, g.name, g.description, g.organization, g.color, g.is_active, g.created_at,
                   COUNT(ug.user_id) AS member_count,
                   COALESCE(
                       json_agg(json_build_object(
                           'id', u.id, 'full_name', u.full_name,
                           'rank', u.rank, 'is_leader', ug.is_leader, 'is_active', u.is_active
                       )) FILTER (WHERE u.id IS NOT NULL), '[]'
                   ) AS members
            FROM groups g
            LEFT JOIN user_groups ug ON ug.group_id = g.id
            LEFT JOIN users u ON u.id = ug.user_id
            GROUP BY g.id
            ORDER BY g.name
            LIMIT $1 OFFSET $2
        """, limit, offset)
    else:
        rows = await conn.fetch("""
            SELECT g.id, g.name, g.description, g.organization, g.color, g.is_active, g.created_at,
                   COUNT(ug.user_id) AS member_count
            FROM groups g
            LEFT JOIN user_groups ug ON ug.group_id = g.id
            GROUP BY g.id
            ORDER BY g.name
            LIMIT $1 OFFSET $2
        """, limit, offset)
    return {'items': [dict(r) for r in rows], 'total': total, 'limit': limit, 'offset': offset}


@router.post('/', status_code=status.HTTP_201_CREATED)
async def create_group(
    body: GroupCreate,
    conn: Annotated[asyncpg.Connection, Depends(get_conn)],
    _: Annotated[asyncpg.Record, Depends(require_role('admin'))],
):
    try:
        row = await conn.fetchrow("""
            INSERT INTO groups (name, description, organization, color) VALUES ($1,$2,$3,$4)
            RETURNING id, name, organization, color
        """, body.name, body.description, body.organization, body.color)
    except asyncpg.UniqueViolationError:
        raise HTTPException(status_code=409, detail='Group name already exists')
    return dict(row)


@router.get('/{group_id}')
async def get_group(
    group_id: UUID,
    conn: Annotated[asyncpg.Connection, Depends(get_conn)],
    _: Annotated[asyncpg.Record, Depends(get_current_user)],
):
    group = await conn.fetchrow('SELECT * FROM groups WHERE id = $1', group_id)
    if group is None:
        raise HTTPException(status_code=404, detail='Group not found')
    members = await conn.fetch("""
        SELECT u.id, u.full_name, u.rank, u.is_active, ug.is_leader
        FROM user_groups ug
        JOIN users u ON u.id = ug.user_id
        WHERE ug.group_id = $1
        ORDER BY u.full_name
    """, group_id)
    return {**dict(group), 'members': [dict(m) for m in members]}


@router.put('/{group_id}')
async def update_group(
    group_id: UUID,
    body: GroupUpdate,
    conn: Annotated[asyncpg.Connection, Depends(get_conn)],
    _: Annotated[asyncpg.Record, Depends(require_role('admin'))],
):
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail='No fields to update')
    fields = ', '.join(f'{k} = ${i+2}' for i, k in enumerate(updates))
    row = await conn.fetchrow(
        f'UPDATE groups SET {fields}, updated_at = NOW() WHERE id = $1 RETURNING id, name, organization, color',
        group_id, *updates.values(),
    )
    if row is None:
        raise HTTPException(status_code=404, detail='Group not found')
    return dict(row)


@router.patch('/{group_id}/deactivate', status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_group(
    group_id: UUID,
    conn: Annotated[asyncpg.Connection, Depends(get_conn)],
    _: Annotated[asyncpg.Record, Depends(require_role('admin'))],
):
    await conn.execute('UPDATE groups SET is_active = FALSE WHERE id = $1', group_id)


@router.patch('/{group_id}/reactivate', status_code=status.HTTP_204_NO_CONTENT)
async def reactivate_group(
    group_id: UUID,
    conn: Annotated[asyncpg.Connection, Depends(get_conn)],
    _: Annotated[asyncpg.Record, Depends(require_role('admin'))],
):
    await conn.execute('UPDATE groups SET is_active = TRUE WHERE id = $1', group_id)


@router.delete('/{group_id}', status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(
    group_id: UUID,
    conn: Annotated[asyncpg.Connection, Depends(get_conn)],
    _: Annotated[asyncpg.Record, Depends(require_role('admin'))],
):
    await conn.execute('DELETE FROM groups WHERE id = $1', group_id)


@router.post('/{group_id}/members', status_code=status.HTTP_201_CREATED)
async def add_member(
    group_id: UUID,
    body: MemberAdd,
    conn: Annotated[asyncpg.Connection, Depends(get_conn)],
    _: Annotated[asyncpg.Record, Depends(require_role('admin'))],
):
    try:
        await conn.execute("""
            INSERT INTO user_groups (user_id, group_id, is_leader) VALUES ($1,$2,$3)
            ON CONFLICT (user_id, group_id) DO UPDATE SET is_leader = EXCLUDED.is_leader
        """, body.user_id, group_id, body.is_leader)
    except asyncpg.ForeignKeyViolationError:
        raise HTTPException(status_code=404, detail='User not found')
    return {'user_id': body.user_id, 'group_id': group_id, 'is_leader': body.is_leader}


@router.delete('/{group_id}/members/{user_id}', status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    group_id: UUID,
    user_id: UUID,
    conn: Annotated[asyncpg.Connection, Depends(get_conn)],
    _: Annotated[asyncpg.Record, Depends(require_role('admin'))],
):
    await conn.execute(
        'DELETE FROM user_groups WHERE group_id = $1 AND user_id = $2',
        group_id, user_id,
    )
