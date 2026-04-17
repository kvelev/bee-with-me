"""
Unit tests for auth.py pure functions — no DB, no HTTP.
"""

import time

import pytest
from jose import jwt

from backend.auth import (
    ALGORITHM,
    create_access_token,
    hash_password,
    verify_password,
)
from backend.config import settings


# ── Password hashing ──────────────────────────────────────────────────────────

def test_hash_is_not_plaintext():
    assert hash_password('hunter2') != 'hunter2'


def test_verify_correct_password():
    hashed = hash_password('correct-horse')
    assert verify_password('correct-horse', hashed) is True


def test_verify_wrong_password():
    hashed = hash_password('correct-horse')
    assert verify_password('wrong', hashed) is False


def test_hash_is_unique_per_call():
    assert hash_password('same') != hash_password('same')


# ── JWT ───────────────────────────────────────────────────────────────────────

def test_token_contains_sub_and_role():
    token = create_access_token('user-123', 'admin')
    payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    assert payload['sub'] == 'user-123'
    assert payload['role'] == 'admin'


def test_token_has_future_expiry():
    token = create_access_token('user-123', 'viewer')
    payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    assert payload['exp'] > time.time()


def test_token_invalid_secret_rejected():
    token = create_access_token('user-123', 'admin')
    with pytest.raises(Exception):
        jwt.decode(token, 'wrong_secret', algorithms=[ALGORITHM])


def test_different_users_get_different_tokens():
    t1 = create_access_token('user-1', 'viewer')
    t2 = create_access_token('user-2', 'viewer')
    assert t1 != t2
