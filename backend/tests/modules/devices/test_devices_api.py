"""Devices API: list, create default, update, assign, deactivate and the admin gate (mocked DB)."""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from backend.auth import get_current_user

pytestmark = [pytest.mark.Trait("Task", "T112")]


def test_list_returns_rows_with_user_columns(client, mock_conn):
    row = {'id': uuid.uuid4(), 'dev_sn': 5, 'name': 'Bee 5', 'device_type': 'bee', 'is_active': True,
           'created_at': datetime(2026, 10, 1, tzinfo=timezone.utc), 'site_latitude': None, 'site_longitude': None,
           'user_id': uuid.uuid4(), 'user_name': 'Ivan', 'user_rank': 'Sgt'}
    mock_conn.fetch = AsyncMock(return_value=[row])
    resp = client.get('/api/devices/')
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]['id'] == str(row['id'])
    assert body[0]['user_id'] == str(row['user_id'])
    assert body[0]['user_name'] == 'Ivan'
    assert body[0]['user_rank'] == 'Sgt'
    assert body[0]['site_latitude'] is None
    assert 'ORDER BY d.device_type, d.dev_sn' in mock_conn.fetch.call_args.args[0]


def test_create_defaults_type_to_bee(client, mock_conn):
    did = uuid.uuid4()
    mock_conn.fetchrow = AsyncMock(return_value={'id': did, 'dev_sn': 5, 'name': None, 'device_type': 'bee'})
    resp = client.post('/api/devices/', json={'dev_sn': 5})
    assert resp.status_code == 201
    assert resp.json() == {'id': str(did), 'dev_sn': 5, 'name': None, 'device_type': 'bee'}
    assert mock_conn.fetchrow.call_args.args[1:] == (5, None, 'bee', None)


def test_update_without_fields_is_400_and_unknown_is_404(client, mock_conn):
    did = uuid.uuid4()
    resp = client.put(f'/api/devices/{did}', json={})
    assert resp.status_code == 400
    assert resp.json()['detail'] == 'No fields to update'
    mock_conn.fetchrow.assert_not_called()

    mock_conn.fetchrow = AsyncMock(return_value=None)
    resp = client.put(f'/api/devices/{did}', json={'name': 'X'})
    assert resp.status_code == 404
    assert resp.json()['detail'] == 'Device not found'


def test_assign_stamps_assigned_at_only_on_change(client, mock_conn):
    did, uid = uuid.uuid4(), uuid.uuid4()
    resp = client.put(f'/api/devices/{did}/assign', json={'user_id': str(uid)})
    assert resp.status_code == 200
    assert resp.json() == {'device_id': str(did), 'user_id': str(uid)}
    args = mock_conn.execute.call_args.args
    assert 'assigned_at = CASE WHEN user_id IS DISTINCT FROM $1' in args[0]
    assert args[1:] == (uid, did)


def test_assign_none_detaches(client, mock_conn):
    did = uuid.uuid4()
    resp = client.put(f'/api/devices/{did}/assign', json={'user_id': None})
    assert resp.status_code == 200
    assert resp.json() == {'device_id': str(did), 'user_id': None}
    args = mock_conn.execute.call_args.args
    assert args[1] is None
    assert args[2] == did


def test_deactivate_resolves_rescuer_alerts_and_notifies(client, mock_conn, admin_user, monkeypatch):
    did = uuid.uuid4()
    resolve = AsyncMock(return_value=['a1'])
    notify = AsyncMock()
    monkeypatch.setattr('backend.routers.devices.fire_repository.resolve_disabled_alerts', resolve)
    monkeypatch.setattr('backend.routers.devices.notify_alerts_updated', notify)
    resp = client.delete(f'/api/devices/{did}')
    assert resp.status_code == 204
    assert mock_conn.execute.call_args.args == ('UPDATE devices SET is_active = FALSE WHERE id = $1', did)
    resolve.assert_awaited_once_with(mock_conn, admin_user['id'], device_id=did)
    notify.assert_awaited_once_with(mock_conn, ['a1'])


def test_reactivate_is_204(client, mock_conn):
    did = uuid.uuid4()
    resp = client.post(f'/api/devices/{did}/reactivate')
    assert resp.status_code == 204
    assert mock_conn.execute.call_args.args == ('UPDATE devices SET is_active = TRUE WHERE id = $1', did)


@pytest.mark.parametrize('method,path', [
    ('post', '/api/devices/'),
    ('put', '/api/devices/{id}'),
    ('put', '/api/devices/{id}/assign'),
    ('put', '/api/devices/{id}/location'),
    ('delete', '/api/devices/{id}'),
    ('post', '/api/devices/{id}/reactivate'),
    ('delete', '/api/devices/{id}/permanent'),
])
def test_writes_require_admin(client, mock_conn, viewer_user, test_app, method, path):
    test_app.dependency_overrides[get_current_user] = lambda: viewer_user
    url = path.format(id=uuid.uuid4())
    body = {'post': {'dev_sn': 1}, 'put': {'name': 'x', 'user_id': None}}.get(method)
    resp = client.request(method.upper(), url, json=body)
    assert resp.status_code == 403
    assert mock_conn.mock_calls == []  # no query of any kind before the gate
