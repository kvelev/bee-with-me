"""SOS API: open alerts and resolve (mocked DB)."""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from backend.auth import get_current_user

pytestmark = [pytest.mark.Trait("Task", "T111")]


def test_sos_list_returns_rows_as_dicts(client, mock_conn):
    aid, did = uuid.uuid4(), uuid.uuid4()
    t = datetime(2026, 10, 1, 10, 0, tzinfo=timezone.utc)
    row = {'id': aid, 'device_id': did, 'triggered_at': t, 'dev_sn': 7,
           'device_name': 'Bee 7', 'full_name': 'Ivan', 'rank': 'Sgt'}
    mock_conn.fetch = AsyncMock(return_value=[row])
    resp = client.get('/api/locations/sos')
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]['id'] == str(aid)
    assert body[0]['device_id'] == str(did)
    assert body[0]['dev_sn'] == 7
    assert body[0]['device_name'] == 'Bee 7'
    assert body[0]['full_name'] == 'Ivan'
    assert body[0]['rank'] == 'Sgt'
    assert datetime.fromisoformat(body[0]['triggered_at'].replace('Z', '+00:00')) == t
    assert 'sa.resolved_at IS NULL' in mock_conn.fetch.call_args.args[0]


def test_resolve_updates_only_open_alert_with_user_and_notes(client, mock_conn, admin_user):
    aid = uuid.uuid4()
    resp = client.post(f'/api/locations/sos/{aid}/resolve?notes=ok')
    assert resp.status_code == 200
    assert resp.json() == {'resolved': True}
    args = mock_conn.execute.call_args.args
    assert 'WHERE id = $1 AND resolved_at IS NULL' in args[0]
    assert args[1:] == (aid, admin_user['id'], 'ok')


def test_resolve_allowed_for_any_logged_in_user(client, mock_conn, viewer_user, test_app):
    test_app.dependency_overrides[get_current_user] = lambda: viewer_user
    aid = uuid.uuid4()
    resp = client.post(f'/api/locations/sos/{aid}/resolve')
    assert resp.status_code == 200
    assert resp.json() == {'resolved': True}
    assert mock_conn.execute.call_args.args[1:] == (aid, viewer_user['id'], None)
