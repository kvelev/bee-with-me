import logging
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import httpx
import pytest

from backend.auth import get_current_user
from backend.database import get_conn
from backend.routers import settings as settings_router

pytestmark = pytest.mark.Trait("Task", "T12")

ROW = {'id': 1, 'hq_latitude': None, 'hq_longitude': None, 'is_hq_alarm_enabled': True,
       'is_rescuer_alarm_enabled': True, 'hq_radius_m': 10000, 'rescuer_radius_m': 3000,
       'alarm_max_age_hours': 24, 'repeat_minutes': 5, 'is_rescuer_photo_on_map_enabled': True,
       'updated_by': None,
       'updated_at': datetime(2026, 10, 2, tzinfo=timezone.utc)}
BODY = {k: ROW[k] for k in ('hq_latitude', 'hq_longitude', 'is_hq_alarm_enabled', 'is_rescuer_alarm_enabled',
                            'hq_radius_m', 'rescuer_radius_m', 'alarm_max_age_hours', 'repeat_minutes',
                            'is_rescuer_photo_on_map_enabled')}
# B37: PUT /api/settings now requires the updated_at the client last saw.
BODY = {**BODY, 'expected_updated_at': ROW['updated_at'].isoformat()}


def test_get_settings(client, mock_conn):
    mock_conn.fetchrow = AsyncMock(return_value=ROW)
    body = client.get('/api/settings').json()
    assert body['hq_radius_m'] == 10000 and 'updated_by' not in body


def test_put_settings_saves_and_calls_hook(client, mock_conn, admin_user, monkeypatch):
    calls = []
    monkeypatch.setattr(settings_router, 'after_change', lambda: calls.append(1))
    saved = {**ROW, 'hq_latitude': 42.5, 'hq_longitude': 24.5}
    mock_conn.fetchrow = AsyncMock(return_value=saved)
    resp = client.put('/api/settings', json={**BODY, 'hq_latitude': 42.5, 'hq_longitude': 24.5})
    assert resp.status_code == 200 and resp.json()['hq_latitude'] == 42.5
    args = mock_conn.fetchrow.call_args.args
    assert 42.5 in args and 24.5 in args and admin_user['id'] in args
    assert calls == [1]


@pytest.mark.parametrize('patch', [
    {'hq_radius_m': 99}, {'rescuer_radius_m': 100001}, {'alarm_max_age_hours': 0},
    {'repeat_minutes': 61}, {'hq_latitude': 42.0}, {'hq_latitude': 91, 'hq_longitude': 24},
])
def test_put_settings_validates(client, patch):
    assert client.put('/api/settings', json={**BODY, **patch}).status_code == 422


def test_put_settings_requires_admin(client, viewer_user, test_app):
    test_app.dependency_overrides[get_current_user] = lambda: viewer_user
    assert client.put('/api/settings', json=BODY).status_code == 403


def test_hq_initial_sets_only_when_unset(client, mock_conn):
    mock_conn.fetchrow = AsyncMock(return_value={**ROW, 'hq_latitude': 42.5, 'hq_longitude': 24.5})
    assert client.put('/api/settings/hq-initial', json={'hq_latitude': 42.5, 'hq_longitude': 24.5}).status_code == 200
    sql = mock_conn.fetchrow.call_args.args[0]
    assert 'hq_latitude IS NULL' in sql


def test_hq_initial_conflicts_when_already_set(client, mock_conn):
    mock_conn.fetchrow = AsyncMock(return_value=None)
    resp = client.put('/api/settings/hq-initial', json={'hq_latitude': 42.5, 'hq_longitude': 24.5})
    assert resp.status_code == 409 and resp.json() == {'detail': 'hq_already_set'}


# --- B37 / B36 ---------------------------------------------------------------------------------

B37 = pytest.mark.Trait("Bug", "B37")
B36 = pytest.mark.Trait("Bug", "B36")


def _hook(monkeypatch):
    calls = []
    monkeypatch.setattr(settings_router, 'after_change', lambda: calls.append(1))
    return calls


@B37
def test_put_stale_expected_updated_at_is_409_and_writes_nothing(client, mock_conn, monkeypatch):
    calls = _hook(monkeypatch)
    mock_conn.fetchrow = AsyncMock(return_value=None)   # WHERE ... updated_at = $11 matched nothing
    mock_conn.fetchval = AsyncMock(return_value=1)      # but the row exists
    resp = client.put('/api/settings', json=BODY)
    assert resp.status_code == 409 and resp.json() == {'detail': 'settings_stale'}
    sql = mock_conn.fetchrow.call_args.args[0]
    assert 'updated_at = $11' in sql
    assert mock_conn.fetchrow.call_args.args[-1] == ROW['updated_at']
    assert calls == []


@B37
def test_put_matching_expected_updated_at_is_200(client, mock_conn, monkeypatch):
    calls = _hook(monkeypatch)
    mock_conn.fetchrow = AsyncMock(return_value=ROW)
    assert client.put('/api/settings', json=BODY).status_code == 200
    assert calls == [1]


@B37
def test_put_without_expected_updated_at_is_422(client, mock_conn):
    body = {k: v for k, v in BODY.items() if k != 'expected_updated_at'}
    assert client.put('/api/settings', json=body).status_code == 422
    mock_conn.fetchrow.assert_not_called()


@B37
def test_put_hq_changes_only_hq(client, mock_conn, admin_user, monkeypatch):
    calls = _hook(monkeypatch)
    mock_conn.fetchrow = AsyncMock(return_value={**ROW, 'hq_latitude': 42.5, 'hq_longitude': 24.5})
    resp = client.put('/api/settings/hq', json={'hq_latitude': 42.5, 'hq_longitude': 24.5})
    assert resp.status_code == 200 and resp.json()['hq_latitude'] == 42.5
    sql = mock_conn.fetchrow.call_args.args[0]
    assert 'hq_latitude' in sql and 'is_hq_alarm_enabled' not in sql and 'radius' not in sql
    assert 'updated_at =' not in sql
    assert mock_conn.fetchrow.call_args.args[1:] == (42.5, 24.5, admin_user['id'])
    assert calls == [1]


@B37
def test_put_hq_can_clear_with_nulls(client, mock_conn):
    mock_conn.fetchrow = AsyncMock(return_value=ROW)
    resp = client.put('/api/settings/hq', json={'hq_latitude': None, 'hq_longitude': None})
    assert resp.status_code == 200 and resp.json()['hq_latitude'] is None


@B37
@pytest.mark.parametrize('body', [
    {'hq_latitude': 42.5, 'hq_longitude': None}, {'hq_latitude': 91, 'hq_longitude': 24},
    {'hq_latitude': '42.5', 'hq_longitude': 24.5}, {'hq_latitude': 42.5},
])
def test_put_hq_validates(client, body):
    assert client.put('/api/settings/hq', json=body).status_code == 422


@B37
def test_put_hq_requires_admin(client, mock_conn, viewer_user, test_app):
    test_app.dependency_overrides[get_current_user] = lambda: viewer_user
    resp = client.put('/api/settings/hq', json={'hq_latitude': 42.5, 'hq_longitude': 24.5})
    assert resp.status_code == 403
    mock_conn.fetchrow.assert_not_called()


@B37
def test_hq_initial_requires_nobody_saved_settings(client, mock_conn):
    mock_conn.fetchrow = AsyncMock(return_value=None)
    mock_conn.fetchval = AsyncMock(return_value=1)
    resp = client.put('/api/settings/hq-initial', json={'hq_latitude': 42.5, 'hq_longitude': 24.5})
    assert resp.status_code == 409 and resp.json() == {'detail': 'hq_already_set'}
    sql = mock_conn.fetchrow.call_args.args[0]
    assert 'hq_latitude IS NULL' in sql and 'updated_by IS NULL' in sql


@B37
@B36
def test_missing_row_is_503_for_get_put_hq_and_hq_initial(client, mock_conn, monkeypatch):
    calls = _hook(monkeypatch)
    mock_conn.fetchrow = AsyncMock(return_value=None)
    mock_conn.fetchval = AsyncMock(return_value=None)   # existence probe: no settings row
    point = {'hq_latitude': 42.5, 'hq_longitude': 24.5}
    for resp in (client.get('/api/settings'), client.put('/api/settings', json=BODY),
                 client.put('/api/settings/hq', json=point),
                 client.put('/api/settings/hq-initial', json=point)):
        assert resp.status_code == 503 and resp.json() == {'detail': 'settings_missing'}
    assert calls == []


@B37
@pytest.mark.parametrize('patch', [
    {'is_hq_alarm_enabled': 'false'}, {'is_rescuer_alarm_enabled': 0}, {'is_hq_alarm_enabled': 1},
    {'hq_radius_m': '5000'}, {'repeat_minutes': True}, {'alarm_max_age_hours': 24.0},
])
def test_put_settings_is_strict_about_types(client, mock_conn, patch):
    assert client.put('/api/settings', json={**BODY, **patch}).status_code == 422
    mock_conn.fetchrow.assert_not_called()


@B37
def test_audit_log_has_no_coordinates(client, mock_conn, admin_user, caplog):
    mock_conn.fetchrow = AsyncMock(return_value={**ROW, 'hq_latitude': 42.123456, 'hq_longitude': 24.654321})
    with caplog.at_level(logging.INFO, logger='backend.routers.settings'):
        client.put('/api/settings', json={**BODY, 'hq_latitude': 42.123456, 'hq_longitude': 24.654321})
        client.put('/api/settings/hq', json={'hq_latitude': 42.123456, 'hq_longitude': 24.654321})
    text = ' | '.join(r.getMessage() for r in caplog.records)
    assert 'settings updated by user %s' % admin_user['id'] in text
    assert 'HQ set by user %s' % admin_user['id'] in text
    assert '42.1' not in text and '24.6' not in text


@pytest.mark.db
@pytest.mark.asyncio
@pytest.mark.Trait("Bug", "B39")
async def test_put_with_the_returned_updated_at_succeeds_once_then_is_stale(
        migrated_conn, test_app, admin_user, monkeypatch):
    """Real Postgres: the ISO updated_at from GET round-trips into the WHERE clause (microseconds,
    timezone), so the first PUT matches and the second, with the same stale value, is a 409."""
    monkeypatch.setattr(settings_router, 'after_change', None)
    await migrated_conn.execute(
        "INSERT INTO users (id, username, full_name, role) VALUES ($1, 'b39admin', 'B39 Admin', 'admin')",
        admin_user['id'])

    async def _get_conn():
        yield migrated_conn

    async def _get_current_user():
        return admin_user

    test_app.dependency_overrides[get_conn] = _get_conn
    test_app.dependency_overrides[get_current_user] = _get_current_user
    try:
        transport = httpx.ASGITransport(app=test_app)
        async with httpx.AsyncClient(transport=transport, base_url='http://test') as http:
            got = (await http.get('/api/settings')).json()
            body = {k: got[k] for k in BODY if k != 'expected_updated_at'}
            body['hq_radius_m'] = 5000
            body['expected_updated_at'] = got['updated_at']

            first = await http.put('/api/settings', json=body)
            assert first.status_code == 200, first.text
            assert first.json()['hq_radius_m'] == 5000
            assert first.json()['updated_at'] != got['updated_at']   # the trigger moved the version

            second = await http.put('/api/settings', json={**body, 'hq_radius_m': 7000})
            assert second.status_code == 409
            assert second.json() == {'detail': 'settings_stale'}
            assert await migrated_conn.fetchval('SELECT hq_radius_m FROM settings WHERE id = 1') == 5000
    finally:
        test_app.dependency_overrides.clear()


F1 = pytest.mark.Trait("Task", "F1")


@F1
def test_get_returns_rescuer_photo_flag(client, mock_conn):
    mock_conn.fetchrow = AsyncMock(return_value={**ROW, 'is_rescuer_photo_on_map_enabled': False})
    assert client.get('/api/settings').json()['is_rescuer_photo_on_map_enabled'] is False


@F1
def test_put_requires_rescuer_photo_flag(client, mock_conn):
    body = {k: v for k, v in BODY.items() if k != 'is_rescuer_photo_on_map_enabled'}
    assert client.put('/api/settings', json=body).status_code == 422
    mock_conn.fetchrow.assert_not_called()


@F1
@pytest.mark.parametrize('value', ['true', 1, 0, None])
def test_put_rejects_non_boolean_rescuer_photo_flag(client, mock_conn, value):
    resp = client.put('/api/settings', json={**BODY, 'is_rescuer_photo_on_map_enabled': value})
    assert resp.status_code == 422
    mock_conn.fetchrow.assert_not_called()


@F1
def test_put_saves_rescuer_photo_flag(client, mock_conn):
    mock_conn.fetchrow = AsyncMock(return_value={**ROW, 'is_rescuer_photo_on_map_enabled': False})
    resp = client.put('/api/settings', json={**BODY, 'is_rescuer_photo_on_map_enabled': False})
    assert resp.status_code == 200 and resp.json()['is_rescuer_photo_on_map_enabled'] is False
    sql, *args = mock_conn.fetchrow.call_args.args
    assert 'is_rescuer_photo_on_map_enabled = $9' in sql and 'updated_at = $11' in sql
    assert args[8] is False


# ---- Clearing HQ ends its alerts, so an HQ set again alarms afresh ----

def test_put_hq_clear_resolves_open_hq_alerts_and_broadcasts(client, mock_conn, admin_user, monkeypatch):
    resolved, notified = [], []

    async def fake_resolve(conn, by):
        resolved.append(by)
        return ['a1']

    async def fake_notify(conn, ids):
        notified.append(list(ids))

    monkeypatch.setattr(settings_router.fire_repository, 'resolve_hq_alerts', fake_resolve)
    monkeypatch.setattr(settings_router, 'notify_alerts_updated', fake_notify)
    mock_conn.fetchrow = AsyncMock(return_value=ROW)
    resp = client.put('/api/settings/hq', json={'hq_latitude': None, 'hq_longitude': None})
    assert resp.status_code == 200
    assert resolved == [admin_user['id']] and notified == [['a1']]


@pytest.mark.parametrize('url,body', [
    ('/api/settings/hq', {'hq_latitude': 42.5, 'hq_longitude': 24.5}),
    ('/api/settings', {**BODY, 'hq_latitude': 42.5, 'hq_longitude': 24.5}),
])
def test_setting_hq_leaves_hq_alerts_alone(client, mock_conn, monkeypatch, url, body):
    resolved = []

    async def fake_resolve(conn, by):
        resolved.append(by)
        return []

    monkeypatch.setattr(settings_router.fire_repository, 'resolve_hq_alerts', fake_resolve)
    mock_conn.fetchrow = AsyncMock(return_value={**ROW, 'hq_latitude': 42.5, 'hq_longitude': 24.5})
    assert client.put(url, json=body).status_code == 200
    assert resolved == []


def test_put_settings_clearing_hq_resolves_hq_alerts(client, mock_conn, admin_user, monkeypatch):
    resolved = []

    async def fake_resolve(conn, by):
        resolved.append(by)
        return []

    monkeypatch.setattr(settings_router.fire_repository, 'resolve_hq_alerts', fake_resolve)
    mock_conn.fetchrow = AsyncMock(return_value=ROW)
    assert client.put('/api/settings', json=BODY).status_code == 200   # BODY has HQ null
    assert resolved == [admin_user['id']]


def test_stale_put_settings_resolves_nothing(client, mock_conn, monkeypatch):
    resolved = []

    async def fake_resolve(conn, by):
        resolved.append(by)
        return []

    monkeypatch.setattr(settings_router.fire_repository, 'resolve_hq_alerts', fake_resolve)
    mock_conn.fetchrow = AsyncMock(return_value=None)
    mock_conn.fetchval = AsyncMock(return_value=1)   # row exists: 409 settings_stale
    assert client.put('/api/settings', json=BODY).status_code == 409
    assert resolved == []
