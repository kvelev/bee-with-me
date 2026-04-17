"""
Tests for the dev simulation endpoints.
"""

import uuid
from unittest.mock import AsyncMock, patch


# ── GET /api/test/devices ─────────────────────────────────────────────────────

def test_list_devices_empty(client, mock_conn):
    mock_conn.fetch = AsyncMock(return_value=[])
    resp = client.get('/api/test/devices')
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_devices_returns_rows(client, mock_conn):
    did = str(uuid.uuid4())
    mock_conn.fetch = AsyncMock(return_value=[
        {'id': did, 'dev_sn': 1234, 'name': 'Unit-01', 'user_name': 'Alpha'},
    ])
    resp = client.get('/api/test/devices')
    assert resp.status_code == 200
    assert resp.json()[0]['dev_sn'] == 1234


# ── POST /api/test/simulate ───────────────────────────────────────────────────

def test_simulate_unknown_device(client, mock_conn):
    mock_conn.fetchrow = AsyncMock(return_value=None)
    resp = client.post('/api/test/simulate', json={'device_id': str(uuid.uuid4())})
    assert resp.status_code == 404


def test_simulate_success(client, mock_conn):
    did = uuid.uuid4()
    uid = uuid.uuid4()
    event_id = uuid.uuid4()

    mock_conn.fetchrow = AsyncMock(side_effect=[
        {'id': did, 'user_id': uid},              # device lookup
        {'id': event_id},                          # INSERT RETURNING id
    ])
    mock_conn.execute = AsyncMock(return_value=None)

    resp = client.post('/api/test/simulate', json={
        'device_id': str(did),
        'lat': 42.698,
        'lon': 23.322,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body['lat'] == 42.698
    assert body['lon'] == 23.322
    assert 'mgrs' in body
    assert 'inserted' in body


def test_simulate_random_coords_in_bulgaria(client, mock_conn):
    did = uuid.uuid4()
    uid = uuid.uuid4()
    event_id = uuid.uuid4()

    mock_conn.fetchrow = AsyncMock(side_effect=[
        {'id': did, 'user_id': uid},
        {'id': event_id},
    ])
    mock_conn.execute = AsyncMock(return_value=None)

    resp = client.post('/api/test/simulate', json={'device_id': str(did)})
    assert resp.status_code == 200
    body = resp.json()
    # coords should be inside Bulgaria bounding box
    assert 41.2 <= body['lat'] <= 44.2
    assert 22.3 <= body['lon'] <= 28.6
