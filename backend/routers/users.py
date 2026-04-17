import os
import uuid
from typing import Annotated
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from pydantic import BaseModel

from ..auth import get_current_user, hash_password, require_role
from ..database import get_conn

router = APIRouter(prefix='/api/users', tags=['users'])

UPLOAD_DIR = 'backend/uploads'
ALLOWED_TYPES = {'image/jpeg', 'image/png', 'image/webp'}


class UserCreate(BaseModel):
    first_name: str
    last_name: str
    phone: str
    pin: str | None = None
    username: str | None = None
    password: str | None = None
    email: str | None = None
    rank: str | None = None
    blood_type: str | None = None
    notes: str | None = None
    role: str = 'viewer'


class UserUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    pin: str | None = None
    email: str | None = None
    rank: str | None = None
    blood_type: str | None = None
    notes: str | None = None
    role: str | None = None
    is_active: bool | None = None
    password: str | None = None
    clear_login: bool | None = None   # set True to remove username + password


@router.get('/')
async def list_users(
    conn: Annotated[asyncpg.Connection, Depends(get_conn)],
    _: Annotated[asyncpg.Record, Depends(get_current_user)],
):
    rows = await conn.fetch("""
        SELECT u.id, u.username, u.full_name, u.first_name, u.last_name,
               u.email, u.phone, u.rank, u.blood_type, u.photo_url,
               u.role, u.is_active, u.notes, u.created_at,
               COALESCE(
                   json_agg(json_build_object('id', g.id, 'name', g.name, 'color', g.color, 'is_leader', ug.is_leader))
                   FILTER (WHERE g.id IS NOT NULL), '[]'
               ) AS groups
        FROM users u
        LEFT JOIN user_groups ug ON ug.user_id = u.id
        LEFT JOIN groups g ON g.id = ug.group_id
        GROUP BY u.id
        ORDER BY u.full_name
    """)
    return [dict(r) for r in rows]


@router.post('/', status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate,
    conn: Annotated[asyncpg.Connection, Depends(get_conn)],
    _: Annotated[asyncpg.Record, Depends(require_role('admin'))],
):
    pw_hash  = hash_password(body.password) if body.password else None
    pin_hash = hash_password(body.pin) if body.pin else None
    full_name = f'{body.first_name} {body.last_name}'.strip()
    try:
        row = await conn.fetchrow("""
            INSERT INTO users (username, password_hash, pin_hash, first_name, last_name, full_name,
                               email, phone, rank, blood_type, notes, role)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
            RETURNING id, username, full_name, role
        """, body.username, pw_hash, pin_hash, body.first_name, body.last_name, full_name,
            body.email, body.phone, body.rank, body.blood_type, body.notes, body.role)
    except asyncpg.UniqueViolationError:
        raise HTTPException(status_code=409, detail='Username already exists')
    return dict(row)


@router.get('/{user_id}')
async def get_user(
    user_id: UUID,
    conn: Annotated[asyncpg.Connection, Depends(get_conn)],
    _: Annotated[asyncpg.Record, Depends(get_current_user)],
):
    row = await conn.fetchrow("""
        SELECT u.id, u.username, u.full_name, u.email, u.phone, u.rank,
               u.blood_type, u.photo_url, u.notes, u.role, u.is_active, u.created_at,
               COALESCE(
                   json_agg(json_build_object('id', g.id, 'name', g.name, 'color', g.color,
                                              'is_leader', ug.is_leader))
                   FILTER (WHERE g.id IS NOT NULL), '[]'
               ) AS groups
        FROM users u
        LEFT JOIN user_groups ug ON ug.user_id = u.id
        LEFT JOIN groups g ON g.id = ug.group_id
        WHERE u.id = $1
        GROUP BY u.id
    """, user_id)
    if row is None:
        raise HTTPException(status_code=404, detail='User not found')
    return dict(row)


@router.put('/{user_id}')
async def update_user(
    user_id: UUID,
    body: UserUpdate,
    conn: Annotated[asyncpg.Connection, Depends(get_conn)],
    _: Annotated[asyncpg.Record, Depends(require_role('admin'))],
):
    updates = body.model_dump(exclude_none=True)
    clear_login = updates.pop('clear_login', False)

    if 'password' in updates:
        updates['password_hash'] = hash_password(updates.pop('password'))
    if 'pin' in updates:
        updates['pin_hash'] = hash_password(updates.pop('pin'))
    if 'first_name' in updates or 'last_name' in updates:
        existing = await conn.fetchrow('SELECT first_name, last_name FROM users WHERE id = $1', user_id)
        fn = updates.get('first_name', existing['first_name'] or '')
        ln = updates.get('last_name',  existing['last_name']  or '')
        updates['full_name'] = f'{fn} {ln}'.strip()

    if not updates and not clear_login:
        raise HTTPException(status_code=400, detail='No fields to update')

    # Build SET clause — parameterised fields first, then explicit NULLs
    set_parts = [f'{k} = ${i + 2}' for i, k in enumerate(updates)]
    values    = list(updates.values())
    if clear_login:
        set_parts.extend(['username = NULL', 'password_hash = NULL'])

    row = await conn.fetchrow(
        f'UPDATE users SET {", ".join(set_parts)}, updated_at = NOW() WHERE id = $1 '
        f'RETURNING id, username, full_name, role',
        user_id, *values,
    )
    if row is None:
        raise HTTPException(status_code=404, detail='User not found')
    return dict(row)


@router.post('/{user_id}/photo')
async def upload_photo(
    user_id: UUID,
    file: Annotated[UploadFile, File()],
    conn: Annotated[asyncpg.Connection, Depends(get_conn)],
    _: Annotated[asyncpg.Record, Depends(require_role('admin'))],
):
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail='Only JPEG, PNG and WebP images are allowed')

    ext = file.filename.rsplit('.', 1)[-1].lower()
    filename = f'{uuid.uuid4()}.{ext}'
    path = os.path.join(UPLOAD_DIR, filename)

    with open(path, 'wb') as f:
        f.write(await file.read())

    photo_url = f'/uploads/{filename}'
    await conn.execute('UPDATE users SET photo_url = $1 WHERE id = $2', photo_url, user_id)
    return {'photo_url': photo_url}


@router.patch('/{user_id}/deactivate', status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_user(
    user_id: UUID,
    conn: Annotated[asyncpg.Connection, Depends(get_conn)],
    _: Annotated[asyncpg.Record, Depends(require_role('admin'))],
):
    await conn.execute('UPDATE users SET is_active = FALSE WHERE id = $1', user_id)


@router.patch('/{user_id}/reactivate', status_code=status.HTTP_204_NO_CONTENT)
async def reactivate_user(
    user_id: UUID,
    conn: Annotated[asyncpg.Connection, Depends(get_conn)],
    _: Annotated[asyncpg.Record, Depends(require_role('admin'))],
):
    await conn.execute('UPDATE users SET is_active = TRUE WHERE id = $1', user_id)


@router.delete('/{user_id}', status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: UUID,
    conn: Annotated[asyncpg.Connection, Depends(get_conn)],
    _: Annotated[asyncpg.Record, Depends(require_role('admin'))],
):
    # Null-out FK columns that have no ON DELETE clause
    await conn.execute('UPDATE location_events SET user_id = NULL WHERE user_id = $1', user_id)
    await conn.execute(
        'UPDATE sos_alerts SET user_id = NULL WHERE user_id = $1', user_id
    )
    await conn.execute(
        'UPDATE sos_alerts SET resolved_by = NULL WHERE resolved_by = $1', user_id
    )
    # user_groups  → ON DELETE CASCADE (auto)
    # devices.user_id → ON DELETE SET NULL (auto)
    await conn.execute('DELETE FROM users WHERE id = $1', user_id)
