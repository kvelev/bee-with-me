"""
HTTP-level tests for POST /api/auth/login and GET /api/auth/me.
Uses the shared client fixture (mocked DB, no real PostgreSQL).
"""

import uuid
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.auth import create_access_token, hash_password, get_current_user
from backend.database import get_conn
from backend.routers import auth as auth_router


# ── Isolated app for login tests (needs real get_current_user flow) ───────────

_login_app = FastAPI()
_login_app.include_router(auth_router.router)


@pytest.fixture()
def login_client(mock_conn):
    async def _get_conn():
        yield mock_conn

    _login_app.dependency_overrides[get_conn] = _get_conn

    with TestClient(_login_app) as c:
        yield c

    _login_app.dependency_overrides.clear()


# ── POST /api/auth/login ──────────────────────────────────────────────────────

def test_login_success(login_client, mock_conn):
    uid = str(uuid.uuid4())
    mock_conn.fetchrow = AsyncMock(return_value={
        'id': uid,
        'password_hash': hash_password('secret'),
        'role': 'admin',
        'is_active': True,
    })

    resp = login_client.post('/api/auth/login', data={'username': 'admin', 'password': 'secret'})
    assert resp.status_code == 200
    body = resp.json()
    assert 'access_token' in body
    assert body['token_type'] == 'bearer'


def test_login_wrong_password(login_client, mock_conn):
    uid = str(uuid.uuid4())
    mock_conn.fetchrow = AsyncMock(return_value={
        'id': uid,
        'password_hash': hash_password('secret'),
        'role': 'admin',
        'is_active': True,
    })

    resp = login_client.post('/api/auth/login', data={'username': 'admin', 'password': 'wrong'})
    assert resp.status_code == 401


def test_login_unknown_user(login_client, mock_conn):
    mock_conn.fetchrow = AsyncMock(return_value=None)
    resp = login_client.post('/api/auth/login', data={'username': 'ghost', 'password': 'x'})
    assert resp.status_code == 401


def test_login_inactive_user(login_client, mock_conn):
    uid = str(uuid.uuid4())
    mock_conn.fetchrow = AsyncMock(return_value={
        'id': uid,
        'password_hash': hash_password('secret'),
        'role': 'viewer',
        'is_active': False,
    })
    resp = login_client.post('/api/auth/login', data={'username': 'admin', 'password': 'secret'})
    assert resp.status_code == 401


# ── GET /api/auth/me ──────────────────────────────────────────────────────────

def test_me_returns_current_user(client, admin_user):
    resp = client.get('/api/auth/me')
    assert resp.status_code == 200
    data = resp.json()
    assert data['username'] == admin_user['username']
    assert data['role'] == 'admin'
