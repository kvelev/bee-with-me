"""Characterisation of the people router: deactivate, reactivate, delete, photo upload, admin gate."""
import uuid
from unittest.mock import AsyncMock

import pytest

from backend.auth import get_current_user

pytestmark = pytest.mark.Trait("Task", "T113")

PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 16


@pytest.fixture(autouse=True)
def upload_dir(monkeypatch, tmp_path):
    """No test in this module may write into the real backend/uploads (volunteer photos)."""
    monkeypatch.setattr('backend.routers.users.UPLOAD_DIR', str(tmp_path))
    return tmp_path


def test_deactivate_resolves_rescuer_alerts_and_notifies(client, mock_conn, admin_user, monkeypatch):
    calls = []

    async def _resolve(*args, **kwargs):
        calls.append('resolve')
        return ['alert-1']

    async def _notify(*args, **kwargs):
        calls.append('notify')

    resolve = AsyncMock(side_effect=_resolve)
    notify = AsyncMock(side_effect=_notify)
    monkeypatch.setattr('backend.routers.users.fire_repository.resolve_disabled_alerts', resolve)
    monkeypatch.setattr('backend.routers.users.notify_alerts_updated', notify)
    uid = uuid.uuid4()

    resp = client.patch(f'/api/users/{uid}/deactivate')

    assert resp.status_code == 204
    mock_conn.execute.assert_awaited_once_with('UPDATE users SET is_active = FALSE WHERE id = $1', uid)
    resolve.assert_awaited_once_with(mock_conn, admin_user['id'], user_id=uid)
    notify.assert_awaited_once_with(mock_conn, ['alert-1'])
    assert calls == ['resolve', 'notify']


def test_reactivate_is_204(client, mock_conn):
    uid = uuid.uuid4()
    resp = client.patch(f'/api/users/{uid}/reactivate')
    assert resp.status_code == 204
    mock_conn.execute.assert_awaited_once_with('UPDATE users SET is_active = TRUE WHERE id = $1', uid)


def test_delete_nulls_positions_and_sos_before_deleting_the_user(client, mock_conn):
    uid = uuid.uuid4()
    resp = client.delete(f'/api/users/{uid}')
    assert resp.status_code == 204
    calls = mock_conn.execute.call_args_list
    assert len(calls) == 4
    assert {c.args[0] for c in calls} == {
        'UPDATE location_events SET user_id = NULL WHERE user_id = $1',
        'UPDATE sos_alerts SET user_id = NULL WHERE user_id = $1',
        'UPDATE sos_alerts SET resolved_by = NULL WHERE resolved_by = $1',
        'DELETE FROM users WHERE id = $1',
    }
    assert all(c.args[1] == uid for c in calls)


def test_photo_upload_rejects_non_image(client, mock_conn):
    resp = client.post(f'/api/users/{uuid.uuid4()}/photo', files={'file': ('a.txt', b'hi', 'text/plain')})
    assert resp.status_code == 400
    assert resp.json()['detail'] == 'Only JPEG, PNG and WebP images are allowed'
    mock_conn.execute.assert_not_awaited()


def test_photo_upload_stores_file_and_updates_photo_url(client, mock_conn, upload_dir):
    uid = uuid.uuid4()

    resp = client.post(f'/api/users/{uid}/photo', files={'file': ('Me.PNG', PNG, 'image/png')})

    assert resp.status_code == 200
    photo_url = resp.json()['photo_url']
    assert photo_url.startswith('/uploads/') and photo_url.endswith('.png')
    stored = upload_dir / photo_url.removeprefix('/uploads/')
    uuid.UUID(stored.stem)
    assert stored.read_bytes() == PNG
    mock_conn.execute.assert_awaited_once_with('UPDATE users SET photo_url = $1 WHERE id = $2', photo_url, uid)


@pytest.mark.parametrize('method,path', [
    ('post', '/api/users/'),
    ('put', '/api/users/{id}'),
    ('post', '/api/users/{id}/photo'),
    ('post', '/api/users/import'),
    ('patch', '/api/users/{id}/deactivate'),
    ('patch', '/api/users/{id}/reactivate'),
    ('delete', '/api/users/{id}'),
])
def test_writes_require_admin(client, mock_conn, viewer_user, test_app, method, path):
    test_app.dependency_overrides[get_current_user] = lambda: viewer_user
    kwargs = {}
    if path == '/api/users/':
        kwargs['json'] = {'first_name': 'A', 'last_name': 'B', 'phone': '1'}
    elif method == 'put':
        kwargs['json'] = {'notes': 'x'}
    elif path.endswith('/photo'):
        kwargs['files'] = {'file': ('a.png', PNG, 'image/png')}
    elif path.endswith('/import'):
        kwargs['files'] = {'file': ('v.xlsx', b'x', 'application/octet-stream')}

    resp = getattr(client, method)(path.format(id=uuid.uuid4()), **kwargs)

    assert resp.status_code == 403
    assert mock_conn.mock_calls == []  # no query of any kind before the gate
