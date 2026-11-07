"""Tracking API: live, trail and history (mocked DB)."""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from backend.config import settings

pytestmark = [pytest.mark.Trait("Task", "T111")]


def test_trail_groups_rows_by_device_and_passes_minutes(client, mock_conn):
    d1, d2 = uuid.uuid4(), uuid.uuid4()
    t1 = datetime(2026, 10, 1, 10, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 10, 1, 10, 1, tzinfo=timezone.utc)
    t3 = datetime(2026, 10, 1, 10, 2, tzinfo=timezone.utc)
    mock_conn.fetch = AsyncMock(return_value=[
        {'device_id': d1, 'latitude': 42.1, 'longitude': 24.1, 'recorded_at': t1, 'received_at': t1},
        {'device_id': d1, 'latitude': 42.2, 'longitude': 24.2, 'recorded_at': t2, 'received_at': t2},
        {'device_id': d2, 'latitude': 43.0, 'longitude': 25.0, 'recorded_at': t3, 'received_at': t3},
    ])
    resp = client.get('/api/locations/trail?minutes=15')
    assert resp.status_code == 200
    assert resp.json() == {
        str(d1): [
            {'lat': 42.1, 'lon': 24.1, 'recorded_at': t1.isoformat(), 'received_at': t1.isoformat()},
            {'lat': 42.2, 'lon': 24.2, 'recorded_at': t2.isoformat(), 'received_at': t2.isoformat()},
        ],
        str(d2): [
            {'lat': 43.0, 'lon': 25.0, 'recorded_at': t3.isoformat(), 'received_at': t3.isoformat()},
        ],
    }
    assert mock_conn.fetch.call_args.args[1] == 15


def test_trail_minutes_bounds(client, mock_conn):
    assert client.get('/api/locations/trail?minutes=0').status_code == 422
    assert client.get('/api/locations/trail?minutes=61').status_code == 422
    mock_conn.fetch.assert_not_called()
    assert client.get('/api/locations/trail').status_code == 200
    assert mock_conn.fetch.call_args.args[1] == 30


def test_history_passes_filters_limit_offset(client, mock_conn):
    did = uuid.uuid4()
    mock_conn.fetch = AsyncMock(return_value=[])
    resp = client.get(f'/api/locations/{did}/history',
                      params={'from': '2026-10-01T00:00:00Z', 'to': '2026-10-02T00:00:00Z', 'limit': 10, 'offset': 5})
    assert resp.status_code == 200
    assert resp.json() == []
    assert mock_conn.fetch.call_args.args[1:] == (
        did,
        datetime(2026, 10, 1, tzinfo=timezone.utc),
        datetime(2026, 10, 2, tzinfo=timezone.utc),
        10, 5,
    )
    assert client.get(f'/api/locations/{did}/history?limit=5001').status_code == 422


def test_live_passes_freshness_horizon(client, mock_conn):
    mock_conn.fetch = AsyncMock(return_value=[{'device_id': 'd1', 'groups': '[]'}])
    resp = client.get('/api/locations/live')
    assert resp.status_code == 200
    assert resp.json() == [{'device_id': 'd1', 'groups': []}]
    assert mock_conn.fetch.call_args.args[1] == settings.live_position_max_age_hours
