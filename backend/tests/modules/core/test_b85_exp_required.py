"""B85: a token signed with the real key but without `exp` is refused (refresh and access paths)."""

import pytest
from fastapi import HTTPException
from jose import jwt

from backend.core.auth import ALGORITHM, create_access_token, create_refresh_token, decode_refresh_token
from backend.core.config import settings


def _no_exp(typ: str) -> str:
    return jwt.encode({'sub': 'u1', 'role': 'admin', 'typ': typ}, settings.secret_key, algorithm=ALGORITHM)


@pytest.mark.Trait("Task", "B85")
def test_refresh_token_without_exp_is_401():
    with pytest.raises(HTTPException) as e:
        decode_refresh_token(_no_exp('refresh'))
    assert e.value.status_code == 401
    assert e.value.detail == 'Invalid or expired refresh token'


@pytest.mark.Trait("Task", "B85")
def test_normal_refresh_token_still_works():
    assert decode_refresh_token(create_refresh_token('u1', 'admin'))['sub'] == 'u1'


@pytest.mark.Trait("Task", "B85")
@pytest.mark.asyncio
async def test_access_token_without_exp_is_401():
    from backend.auth import get_current_user
    with pytest.raises(HTTPException) as e:
        await get_current_user(_no_exp('access'), conn=None)
    assert e.value.status_code == 401
    assert e.value.detail == 'Invalid or expired token'


@pytest.mark.Trait("Task", "B85")
def test_jose_enforces_require_exp_option():
    # python-jose 3.5: options={'require_exp': True} makes a missing exp a JWTError
    from jose import JWTError
    with pytest.raises(JWTError):
        jwt.decode(_no_exp('access'), settings.secret_key, algorithms=[ALGORITHM], options={'require_exp': True})
    assert create_access_token('u1', 'admin')
