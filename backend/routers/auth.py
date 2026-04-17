from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from ..auth import create_access_token, get_current_user, hash_password, verify_password
from ..database import get_conn

router = APIRouter(prefix='/api/auth', tags=['auth'])


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = 'bearer'


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
    return TokenResponse(access_token=create_access_token(str(user['id']), user['role']))


@router.get('/me')
async def me(current_user: Annotated[asyncpg.Record, Depends(get_current_user)]):
    return dict(current_user)
