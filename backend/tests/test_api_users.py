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
    assert resp.json() == []


def test_list_users_returns_rows(client, mock_conn):
    uid = str(uuid.uuid4())
    mock_conn.fetch = AsyncMock(return_value=[
        {'id': uid, 'username': 'alpha', 'full_name': 'Alpha User',
         'email': None, 'phone': None, 'rank': 'Sgt', 'blood_type': 'A+',
         'photo_url': None, 'role': 'viewer', 'is_active': True,
         'created_at': None, 'groups': '[]'},
    ])
    resp = client.get('/api/users/')
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]['username'] == 'alpha'


# ── POST /api/users/ ──────────────────────────────────────────────────────────

def test_create_user_success(client, mock_conn):
    uid = str(uuid.uuid4())
    mock_conn.fetchrow = AsyncMock(return_value={
        'id': uid, 'username': 'newguy', 'full_name': 'New Guy', 'role': 'viewer'
    })
    resp = client.post('/api/users/', json={
        'username': 'newguy', 'password': 'pass123', 'full_name': 'New Guy',
    })
    assert resp.status_code == 201
    assert resp.json()['username'] == 'newguy'


def test_create_user_duplicate_username(client, mock_conn):
    mock_conn.fetchrow = AsyncMock(side_effect=asyncpg.UniqueViolationError(
        'duplicate key value',
        position='1',
        detail='Key (username)=(newguy) already exists.',
        schema_name='public',
        table_name='users',
        column_name=None,
        data_type_name=None,
        constraint_name='users_username_key',
    ))
    resp = client.post('/api/users/', json={
        'username': 'newguy', 'password': 'pass', 'full_name': 'Dup',
    })
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
