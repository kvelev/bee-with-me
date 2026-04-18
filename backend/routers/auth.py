from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from ..auth import create_access_token, create_refresh_token, decode_refresh_token, get_current_user, hash_password, verify_password
from ..database import get_conn

router = APIRouter(prefix='/api/auth', tags=['auth'])


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = 'bearer'


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post('/login', response_model=TokenResponse)
async def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    conn: Annotated[asyncpg.Connection, Depends(get_conn)],
):
    user = await conn.fetchrow(
        'SELECT id, password_hash, role, is_active FROM users WHERE username = $1 AND username IS NOT NULL',
        form.username,
    )
    if user is None or not user['is_active'] or not verify_password(form.password, user['password_hash'] or ''):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid credentials')
    uid, role = str(user['id']), user['role']
    return TokenResponse(
        access_token=create_access_token(uid, role),
        refresh_token=create_refresh_token(uid, role),
    )


@router.post('/refresh', response_model=TokenResponse)
async def refresh(
    body: RefreshRequest,
    conn: Annotated[asyncpg.Connection, Depends(get_conn)],
):
    payload = decode_refresh_token(body.refresh_token)
    user = await conn.fetchrow(
        'SELECT id, role, is_active FROM users WHERE id = $1',
        payload['sub'],
    )
    if user is None or not user['is_active']:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='User not found or inactive')
    uid, role = str(user['id']), user['role']
    return TokenResponse(
        access_token=create_access_token(uid, role),
        refresh_token=create_refresh_token(uid, role),
    )


@router.get('/me')
async def me(current_user: Annotated[asyncpg.Record, Depends(get_current_user)]):
    return dict(current_user)
