"""Token functions of the kernel: create and verify JWTs (HS256). No database access, no roles."""

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from jose import JWTError, jwt

from .config import settings

ALGORITHM = 'HS256'


def create_access_token(user_id: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    return jwt.encode(
        {'sub': user_id, 'role': role, 'typ': 'access', 'exp': expire},
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
