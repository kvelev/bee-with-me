"""Characterisation of routers/groups.py: list/get/create/update/members, with a mocked connection."""

import uuid
from unittest.mock import AsyncMock

import asyncpg
import pytest

from backend.auth import get_current_user

pytestmark = [pytest.mark.Trait("Task", "T110")]

GID = uuid.uuid4()
UID = uuid.uuid4()


def _group_row(**extra):
    return {'id': GID, 'name': 'Alpha', 'description': None, 'organization': 'ASP',
            'color': '#3388ff', 'is_active': True, 'created_at': '2026-10-01T00:00:00Z', **extra}


def test_list_without_members_returns_envelope_and_member_count(client, mock_conn):
    mock_conn.fetchval = AsyncMock(return_value=2)
    mock_conn.fetch = AsyncMock(return_value=[_group_row(member_count=3)])
    resp = client.get('/api/groups/')
    assert resp.status_code == 200
    body = resp.json()
    assert body['total'] == 2 and body['limit'] == 100 and body['offset'] == 0
    assert len(body['items']) == 1
    assert body['items'][0]['member_count'] == 3
    assert body['items'][0]['name'] == 'Alpha'
    assert 'members' not in body['items'][0]
    assert 'json_agg' not in mock_conn.fetch.call_args.args[0]


def test_list_with_members_decodes_json_text_to_list(client, mock_conn):
    mock_conn.fetchval = AsyncMock(return_value=1)
    members = '[{"id":"u1","full_name":"A","rank":null,"is_leader":true,"is_active":true}]'
    mock_conn.fetch = AsyncMock(return_value=[_group_row(member_count=1, members=members)])
    resp = client.get('/api/groups/?include_members=true')
    assert resp.status_code == 200
    item = resp.json()['items'][0]
    assert isinstance(item['members'], list)
    assert item['members'][0]['is_leader'] is True
    assert item['members'][0]['full_name'] == 'A'
    assert 'json_agg' in mock_conn.fetch.call_args.args[0]


def test_list_passes_limit_and_offset_as_parameters(client, mock_conn):
    mock_conn.fetchval = AsyncMock(return_value=0)
    resp = client.get('/api/groups/?limit=5&offset=10')
    assert resp.status_code == 200
    assert resp.json()['limit'] == 5 and resp.json()['offset'] == 10
    assert mock_conn.fetch.call_args.args[1:] == (5, 10)
    assert 'LIMIT $1 OFFSET $2' in mock_conn.fetch.call_args.args[0]
    assert client.get('/api/groups/?limit=0').status_code == 422
    assert client.get('/api/groups/?limit=501').status_code == 422


def test_create_returns_201_with_row(client, mock_conn):
    mock_conn.fetchrow = AsyncMock(return_value={'id': GID, 'name': 'Alpha', 'organization': 'ASP', 'color': '#ff0000'})
    resp = client.post('/api/groups/', json={'name': 'Alpha', 'organization': 'ASP', 'color': '#ff0000'})
    assert resp.status_code == 201
    assert resp.json() == {'id': str(GID), 'name': 'Alpha', 'organization': 'ASP', 'color': '#ff0000'}
    sql, *args = mock_conn.fetchrow.call_args.args
    assert sql.strip().startswith('INSERT INTO groups')
    assert args == ['Alpha', None, 'ASP', '#ff0000']


def test_create_duplicate_name_is_409(client, mock_conn):
    mock_conn.fetchrow = AsyncMock(side_effect=asyncpg.UniqueViolationError('dup'))
    resp = client.post('/api/groups/', json={'name': 'Alpha'})
    assert resp.status_code == 409
    assert resp.json()['detail'] == 'Group name already exists'


def test_get_unknown_is_404(client, mock_conn):
    mock_conn.fetchrow = AsyncMock(return_value=None)
    resp = client.get(f'/api/groups/{GID}')
    assert resp.status_code == 404
    assert resp.json()['detail'] == 'Group not found'
    mock_conn.fetch.assert_not_called()


def test_get_returns_group_with_members(client, mock_conn):
    mock_conn.fetchrow = AsyncMock(return_value=_group_row())
    mock_conn.fetch = AsyncMock(return_value=[
        {'id': UID, 'full_name': 'A', 'rank': None, 'is_active': True, 'is_leader': True}])
    resp = client.get(f'/api/groups/{GID}')
    assert resp.status_code == 200
    body = resp.json()
    assert body['name'] == 'Alpha'
    assert body['members'] == [{'id': str(UID), 'full_name': 'A', 'rank': None, 'is_active': True, 'is_leader': True}]
    assert mock_conn.fetch.call_args.args[1] == GID


def test_update_with_no_fields_is_400(client, mock_conn):
    resp = client.put(f'/api/groups/{GID}', json={})
    assert resp.status_code == 400
    assert resp.json()['detail'] == 'No fields to update'
    mock_conn.fetchrow.assert_not_called()


def test_update_unknown_is_404(client, mock_conn):
    mock_conn.fetchrow = AsyncMock(return_value=None)
    resp = client.put(f'/api/groups/{GID}', json={'name': 'Bravo'})
    assert resp.status_code == 404
    assert resp.json()['detail'] == 'Group not found'
    sql, *args = mock_conn.fetchrow.call_args.args
    assert 'SET name = $2, updated_at = NOW() WHERE id = $1' in sql
    assert args == [GID, 'Bravo']


def test_deactivate_reactivate_delete_are_204_and_touch_only_groups(client, mock_conn):
    calls = [
        (client.patch(f'/api/groups/{GID}/deactivate'), 'UPDATE groups SET is_active = FALSE'),
        (client.patch(f'/api/groups/{GID}/reactivate'), 'UPDATE groups SET is_active = TRUE'),
        (client.delete(f'/api/groups/{GID}'), 'DELETE FROM groups'),
    ]
    assert [r.status_code for r, _ in calls] == [204, 204, 204]
    executed = [c.args for c in mock_conn.execute.call_args_list]
    assert len(executed) == 3
    for (sql, gid), (_, prefix) in zip(executed, calls):
        assert sql.startswith(prefix)
        assert gid == GID


def test_add_member_upserts_leader_flag(client, mock_conn):
    resp = client.post(f'/api/groups/{GID}/members', json={'user_id': str(UID), 'is_leader': True})
    assert resp.status_code == 201
    assert resp.json() == {'user_id': str(UID), 'group_id': str(GID), 'is_leader': True}
    sql, *args = mock_conn.execute.call_args.args
    assert 'ON CONFLICT (user_id, group_id) DO UPDATE SET is_leader' in sql
    assert args == [UID, GID, True]


def test_add_member_unknown_user_is_404(client, mock_conn):
    mock_conn.execute = AsyncMock(side_effect=asyncpg.ForeignKeyViolationError('fk'))
    resp = client.post(f'/api/groups/{GID}/members', json={'user_id': str(UID)})
    assert resp.status_code == 404
    assert resp.json()['detail'] == 'User not found'


def test_remove_member_is_204(client, mock_conn):
    resp = client.delete(f'/api/groups/{GID}/members/{UID}')
    assert resp.status_code == 204
    sql, *args = mock_conn.execute.call_args.args
    assert sql.startswith('DELETE FROM user_groups')
    assert args == [GID, UID]


@pytest.mark.parametrize('method,path', [
    ('post', '/api/groups/'),
    ('put', '/api/groups/{gid}'),
    ('patch', '/api/groups/{gid}/deactivate'),
    ('delete', '/api/groups/{gid}'),
    ('post', '/api/groups/{gid}/members'),
    ('delete', '/api/groups/{gid}/members/{uid}'),
])
def test_writes_require_admin(client, mock_conn, viewer_user, test_app, method, path):
    test_app.dependency_overrides[get_current_user] = lambda: viewer_user
    url = path.format(gid=GID, uid=UID)
    kwargs = {}
    if method in ('post', 'put'):
        kwargs['json'] = {'name': 'X', 'user_id': str(UID)}
    resp = getattr(client, method)(url, **kwargs)
    assert resp.status_code == 403
    assert resp.json()['detail'] == 'Insufficient permissions'
    mock_conn.execute.assert_not_called()
    mock_conn.fetchrow.assert_not_called()
