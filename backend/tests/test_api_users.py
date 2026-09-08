"""
HTTP-level tests for /api/users endpoints.
"""

import uuid
from unittest.mock import AsyncMock

import asyncpg
import pytest


# ── GET /api/users/ ───────────────────────────────────────────────────────────

def test_list_users_empty(client, mock_conn):
    mock_conn.fetch = AsyncMock(return_value=[])
    resp = client.get('/api/users/')
    assert resp.status_code == 200
    # Paginated envelope, not a bare list
    assert resp.json() == {'items': [], 'total': 0, 'limit': 50, 'offset': 0}


def test_list_users_returns_rows(client, mock_conn):
    uid = str(uuid.uuid4())
    mock_conn.fetchval = AsyncMock(return_value=1)      # SELECT COUNT(*)
    mock_conn.fetch = AsyncMock(return_value=[
        {'id': uid, 'username': 'alpha', 'full_name': 'Alpha User',
         'email': None, 'phone': None, 'rank': 'Sgt', 'blood_type': 'A+',
         'photo_url': None, 'role': 'viewer', 'is_active': True,
         'created_at': None, 'groups': '[]'},
    ])
    resp = client.get('/api/users/')
    assert resp.status_code == 200
    body = resp.json()
    assert body['total'] == 1
    assert len(body['items']) == 1
    assert body['items'][0]['username'] == 'alpha'


def test_list_users_honours_pagination_params(client, mock_conn):
    mock_conn.fetchval = AsyncMock(return_value=120)
    resp = client.get('/api/users/?limit=10&offset=20')
    assert resp.status_code == 200
    body = resp.json()
    assert (body['limit'], body['offset'], body['total']) == (10, 20, 120)


# ── POST /api/users/ ──────────────────────────────────────────────────────────

# UserCreate requires first_name / last_name / phone; full_name is derived server-side.
NEW_USER = {
    'first_name': 'New', 'last_name': 'Guy', 'phone': '+359888123456',
    'username': 'newguy', 'password': 'pass123',
}


def test_create_user_success(client, mock_conn):
    uid = str(uuid.uuid4())
    mock_conn.fetchrow = AsyncMock(return_value={
        'id': uid, 'username': 'newguy', 'full_name': 'New Guy', 'role': 'viewer'
    })
    resp = client.post('/api/users/', json=NEW_USER)
    assert resp.status_code == 201
    assert resp.json()['username'] == 'newguy'


def test_create_user_requires_name_and_phone(client, mock_conn):
    resp = client.post('/api/users/', json={'username': 'newguy', 'password': 'pass123'})
    assert resp.status_code == 422


def test_create_user_duplicate_username(client, mock_conn):
    # asyncpg's exceptions take a positional message only
    mock_conn.fetchrow = AsyncMock(side_effect=asyncpg.UniqueViolationError(
        'duplicate key value violates unique constraint "users_username_key"'
    ))
    resp = client.post('/api/users/', json=NEW_USER)
    assert resp.status_code == 409


# ── GET /api/users/{id} ───────────────────────────────────────────────────────

def test_get_user_not_found(client, mock_conn):
    mock_conn.fetchrow = AsyncMock(return_value=None)
    resp = client.get(f'/api/users/{uuid.uuid4()}')
    assert resp.status_code == 404


def test_get_user_found(client, mock_conn):
    uid = str(uuid.uuid4())
    mock_conn.fetchrow = AsyncMock(return_value={
        'id': uid, 'username': 'alpha', 'full_name': 'Alpha',
        'email': None, 'phone': None, 'rank': None, 'blood_type': None,
        'photo_url': None, 'notes': None, 'role': 'viewer',
        'is_active': True, 'created_at': None, 'groups': '[]',
    })
    resp = client.get(f'/api/users/{uid}')
    assert resp.status_code == 200
    assert resp.json()['id'] == uid


# ── DELETE /api/users/{id} (deactivate) ──────────────────────────────────────

def test_deactivate_user(client, mock_conn):
    mock_conn.execute = AsyncMock(return_value=None)
    resp = client.delete(f'/api/users/{uuid.uuid4()}')
    assert resp.status_code == 204
