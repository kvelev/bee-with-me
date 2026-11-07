from typing import Annotated

import bcrypt as _bcrypt
import asyncpg
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

from .config import settings
from .core.auth import ALGORITHM, create_access_token, create_refresh_token, decode_refresh_token  # noqa: F401  (intentional re-exports)
from .database import get_conn

oauth2_scheme = OAuth2PasswordBearer(tokenUrl='/api/auth/login')


def hash_password(plain: str) -> str:
    return _bcrypt.hashpw(plain.encode(), _bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _bcrypt.checkpw(plain.encode(), hashed.encode())
    except ValueError:
        # bcrypt refuses passwords over 72 bytes and malformed hashes: that is "no match", not a server error
        return False


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
        # A 7-day refresh token must not work as a Bearer token. Tokens without `typ` (issued before it was added)
        # are refused too: those sessions log in once more.
        if payload.get('typ') != 'access':
            raise credentials_error
        # Legacy tokens were issued without an expiry and would otherwise never age out.
        # python-jose skips the expiry check when the claim is absent, so reject explicitly —
        # the client's refresh flow exchanges these for a bounded token on the next 401.
        if 'exp' not in payload:
            raise credentials_error
    except JWTError:
        raise credentials_error

    user = await conn.fetchrow(
        'SELECT id, username, full_name, role, is_active FROM users WHERE id = $1',
        user_id,
    )
    # The role is read from the DB: a role that may no longer log in (LOGIN_ROLES) has no session either.
    if user is None or not user['is_active'] or user['role'] not in settings.login_role_set:
        raise credentials_error
    return user


def require_role(*roles: str):
    async def _check(current_user: Annotated[asyncpg.Record, Depends(get_current_user)]):
        if current_user['role'] not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Insufficient permissions')
        return current_user
    return _check
