import io
import os
import re
import uuid
import xml.etree.ElementTree as ET
from typing import Annotated
from uuid import UUID

import asyncpg
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, status
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
    is_radio_enthusiast: bool = False
    radio_initials: str | None = None


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
    clear_login: bool | None = None
    is_radio_enthusiast: bool | None = None
    radio_initials: str | None = None


@router.get('/')
async def list_users(
    conn: Annotated[asyncpg.Connection, Depends(get_conn)],
    _: Annotated[asyncpg.Record, Depends(get_current_user)],
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    total = await conn.fetchval('SELECT COUNT(*) FROM users')
    rows = await conn.fetch("""
        SELECT u.id, u.username, u.full_name, u.first_name, u.last_name,
               u.email, u.phone, u.rank, u.blood_type, u.photo_url,
               u.is_radio_enthusiast, u.radio_initials,
               u.pin, u.role, u.is_active, u.notes, u.created_at,
               COALESCE(
                   json_agg(json_build_object('id', g.id, 'name', g.name, 'color', g.color, 'is_leader', ug.is_leader))
                   FILTER (WHERE g.id IS NOT NULL), '[]'
               ) AS groups
        FROM users u
        LEFT JOIN user_groups ug ON ug.user_id = u.id
        LEFT JOIN groups g ON g.id = ug.group_id
        GROUP BY u.id
        ORDER BY u.full_name
        LIMIT $1 OFFSET $2
    """, limit, offset)
    return {'items': [dict(r) for r in rows], 'total': total, 'limit': limit, 'offset': offset}


@router.post('/', status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate,
    conn: Annotated[asyncpg.Connection, Depends(get_conn)],
    _: Annotated[asyncpg.Record, Depends(require_role('admin'))],
):
    pw_hash   = hash_password(body.password) if body.password else None
    full_name = f'{body.first_name} {body.last_name}'.strip()
    try:
        row = await conn.fetchrow("""
            INSERT INTO users (username, password_hash, pin, first_name, last_name, full_name,
                               email, phone, rank, blood_type, notes, role,
                               is_radio_enthusiast, radio_initials)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
            RETURNING id, username, full_name, role
        """, body.username, pw_hash, body.pin, body.first_name, body.last_name, full_name,
            body.email, body.phone, body.rank, body.blood_type, body.notes, body.role,
            body.is_radio_enthusiast, body.radio_initials)
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
               u.blood_type, u.photo_url, u.notes, u.pin, u.role, u.is_active, u.created_at,
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


BLOOD_TYPE_MAP = {
    'a+': 'A+', 'a-': 'A−', 'a−': 'A−',
    'b+': 'B+', 'b-': 'B−', 'b−': 'B−',
    'ab+': 'AB+', 'ab-': 'AB−', 'ab−': 'AB−',
    'o+': 'O+', 'o-': 'O−', 'o−': 'O−',
}

def _parse_xml_spreadsheet(raw: bytes) -> pd.DataFrame:
    """Parse Microsoft XML Spreadsheet format (.xls exported by Google Sheets)."""
    text = None
    for enc in ('utf-8-sig', 'utf-16', 'utf-16-le', 'utf-16-be', 'utf-8', 'windows-1251', 'latin-1'):
        try:
            text = raw.decode(enc)
            break
        except Exception:
            continue
    if text is None:
        raise ValueError('Cannot decode file')

    # Strip namespace prefixes so ElementTree finds tags by local name
    text = re.sub(r'\s+xmlns(?::\w+)?="[^"]*"', '', text)
    text = re.sub(r'<(\w+):',  r'<',  text)
    text = re.sub(r'</(\w+):', r'</', text)

    root  = ET.fromstring(text)
    table = root.find('.//Table')
    if table is None:
        raise ValueError('No Table element found in XML')

    rows_data: list[list[str]] = []
    for row_el in table.findall('Row'):
        cells: list[str] = []
        for cell_el in row_el.findall('Cell'):
            # Handle sparse Index attribute
            idx_attr = cell_el.get('Index')
            if idx_attr:
                while len(cells) < int(idx_attr) - 1:
                    cells.append('')
            data_el = cell_el.find('Data')
            cells.append(data_el.text or '' if data_el is not None else '')
        rows_data.append(cells)

    if len(rows_data) < 2:
        raise ValueError('No data rows found')

    width = max(len(r) for r in rows_data)
    for r in rows_data:
        r += [''] * (width - len(r))

    return pd.DataFrame(rows_data[1:], columns=rows_data[0])


def _find_col(columns: list[str], *keywords: str) -> str | None:
    for kw in keywords:
        for col in columns:
            if kw in col.lower():
                return col
    return None

def _split_name(full: str) -> tuple[str, str]:
    parts = full.strip().split()
    if len(parts) == 0:
        return '', ''
    return parts[0], ' '.join(parts[1:])


@router.post('/import')
async def import_volunteers(
    file: Annotated[UploadFile, File()],
    conn: Annotated[asyncpg.Connection, Depends(get_conn)],
    _: Annotated[asyncpg.Record, Depends(require_role('admin'))],
):
    ext = (file.filename or '').rsplit('.', 1)[-1].lower()
    if ext not in ('xls', 'xlsx'):
        raise HTTPException(status_code=400, detail='Only .xls and .xlsx files are accepted')

    raw = await file.read()
    df = None
    engines = ['calamine', 'xlrd', 'openpyxl'] if ext == 'xls' else ['calamine', 'openpyxl', 'xlrd']
    for engine in engines:
        try:
            df = pd.read_excel(io.BytesIO(raw), engine=engine, dtype=str)
            break
        except Exception:
            pass
    if df is None:
        # Last resort: HTML-disguised Excel (Excel Web Archive)
        last_err = None
        for enc in ('utf-8-sig', 'windows-1251', 'cp1252', 'latin-1'):
            try:
                html_str = raw.decode(enc)
                tables = pd.read_html(io.StringIO(html_str))
                if tables:
                    df = tables[0].astype(str)
                    break
            except Exception as e:
                last_err = e
        if df is None:
            # Final fallback: Microsoft XML Spreadsheet format
            try:
                df = _parse_xml_spreadsheet(raw)
            except Exception as e:
                raise HTTPException(status_code=400, detail=f'Could not parse file: {e}')

    df.columns = [str(c).strip() for c in df.columns]
    cols = list(df.columns)

    name_col  = _find_col(cols, 'volunteer', 'name', 'имe', 'доброволец')
    pin_col   = _find_col(cols, 'pin', 'пин')
    phone_col = _find_col(cols, 'phone', 'tel', 'телефон', 'mobile')

    if not name_col:
        raise HTTPException(status_code=400, detail='Could not find a name column (expected "volunteer" or "name")')

    created, skipped = 0, []

    for i, row in df.iterrows():
        row_num = int(i) + 2   # 1-based + header row
        raw_name = str(row.get(name_col, '') or '').strip()
        if not raw_name or raw_name.lower() == 'nan':
            skipped.append({'row': row_num, 'reason': 'empty name'})
            continue

        first_name, last_name = _split_name(raw_name)
        full_name = raw_name

        phone = str(row.get(phone_col, '') or '').strip() if phone_col else ''
        if phone.lower() == 'nan':
            phone = ''

        raw_pin = str(row.get(pin_col, '') or '').strip() if pin_col else ''
        if raw_pin.lower() == 'nan':
            raw_pin = ''
        # Excel sometimes reads numeric PINs as "1234.0" — strip the decimal
        if raw_pin.endswith('.0'):
            raw_pin = raw_pin[:-2]
        pin = raw_pin or None

        exists = await conn.fetchval('SELECT 1 FROM users WHERE full_name = $1', full_name)
        if exists:
            skipped.append({'row': row_num, 'reason': f'already exists: "{full_name}"'})
            continue
        try:
            await conn.execute("""
                INSERT INTO users (first_name, last_name, full_name, phone, pin, role)
                VALUES ($1, $2, $3, $4, $5, 'rescuer')
            """, first_name, last_name, full_name, phone, pin)
            created += 1
        except asyncpg.UniqueViolationError:
            skipped.append({'row': row_num, 'reason': f'duplicate entry for "{full_name}"'})
        except Exception as e:
            skipped.append({'row': row_num, 'reason': str(e)})

    return {'created': created, 'skipped': skipped}


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
