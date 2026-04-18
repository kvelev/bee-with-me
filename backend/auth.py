from datetime import datetime, timedelta, timezone
from typing import Annotated

import bcrypt as _bcrypt
import asyncpg
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

from .config import settings
from .database import get_conn

ALGORITHM = 'HS256'

oauth2_scheme = OAuth2PasswordBearer(tokenUrl='/api/auth/login')


def hash_password(plain: str) -> str:
    return _bcrypt.hashpw(plain.encode(), _bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return _bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(user_id: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    return jwt.encode(
        {'sub': user_id, 'role': role, 'exp': expire, 'typ': 'access'},
        settings.secret_key,
        algorithm=ALGORITHM,
    )


def create_refresh_token(user_id: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    return jwt.encode(
        {'sub': user_id, 'role': role, 'exp': expire, 'typ': 'refresh'},
        settings.secret_key,
        algorithm=ALGORITHM,
    )


def decode_refresh_token(token: str) -> dict:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail='Invalid or expired refresh token',
    )
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        if payload.get('typ') != 'refresh' or payload.get('sub') is None:
            raise credentials_error
        return payload
    except JWTError:
        raise credentials_error


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    conn: Annotated[asyncpg.Connection, Depends(get_conn)],
) -> asyncpg.Record:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail='Invalid or expired token',
        headers={'WWW-Authenticate': 'Bearer'},
    )
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        user_id: str = payload.get('sub')
        if user_id is None:
            raise credentials_error
    except JWTError:
        raise credentials_error

    user = await conn.fetchrow(
        'SELECT id, username, full_name, role, is_active FROM users WHERE id = $1',
        user_id,
    )
    if user is None or not user['is_active']:
        raise credentials_error
    return user


def require_role(*roles: str):
    async def _check(current_user: Annotated[asyncpg.Record, Depends(get_current_user)]):
        if current_user['role'] not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Insufficient permissions')
        return current_user
    return _check
