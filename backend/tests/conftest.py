"""
Shared test fixtures.

A lightweight FastAPI test app is constructed without the full lifespan
(no DB pool, no serial reader, no pg_notify listener) so tests run offline.
"""

import uuid
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.auth import create_access_token, hash_password, get_current_user
from backend.database import get_conn
from backend.routers import auth, devices, groups, locations, users
from backend.routers import test as test_router

# ── Minimal app without lifespan ──────────────────────────────────────────────

_app = FastAPI()
_app.include_router(auth.router)
_app.include_router(users.router)
_app.include_router(groups.router)
_app.include_router(devices.router)
_app.include_router(locations.router)
_app.include_router(test_router.router)


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_user(role: str = 'admin', active: bool = True) -> dict:
    uid = str(uuid.uuid4())
    return {
        'id': uid,
        'username': 'testuser',
        'full_name': 'Test User',
        'role': role,
        'is_active': active,
        'password_hash': hash_password('secret'),
    }


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def mock_conn():
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=None)
    conn.fetch    = AsyncMock(return_value=[])
    conn.execute  = AsyncMock(return_value=None)
    conn.fetchval = AsyncMock(return_value=0)
    return conn


@pytest.fixture()
def admin_user():
    return make_user(role='admin')


@pytest.fixture()
def viewer_user():
    return make_user(role='viewer')


@pytest.fixture()
def client(mock_conn, admin_user):
    """TestClient with mocked DB and pre-authenticated admin user."""

    async def _get_conn():
        yield mock_conn

    async def _get_current_user():
        return admin_user

    _app.dependency_overrides[get_conn] = _get_conn
    _app.dependency_overrides[get_current_user] = _get_current_user

    with TestClient(_app, raise_server_exceptions=True) as c:
        yield c

    _app.dependency_overrides.clear()


@pytest.fixture()
def auth_headers(admin_user):
    token = create_access_token(admin_user['id'], admin_user['role'])
    return {'Authorization': f'Bearer {token}'}
