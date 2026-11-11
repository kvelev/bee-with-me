"""B51: P5 gate backend fixes (zone lost update, login timing, token type, B49 NaN/bytes, dismiss author, gnss_valid).

DB-free here; the SQL-level checks are in test_b51_db.py."""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from jose import jwt

from backend import auth as auth_module
from backend import ws
from backend.auth import create_access_token, create_refresh_token, get_current_user, hash_password
from backend.config import settings
from backend.database import get_conn
from backend.fire import repository
from backend.routers import auth as auth_router
from backend.routers import fire as fire_router

pytestmark = pytest.mark.Trait("Bug", "B51")

T = datetime(2026, 10, 4, 10, 0, 0, 123456, tzinfo=timezone.utc)
HEADERS = {'Content-Type': 'application/json'}


# -- item 1: zone concurrency contract ----------------------------------------------------------------------------

def _zone(**over):
    row = {'id': uuid.uuid4(), 'label': 'Secret label', 'latitude': 42.5, 'longitude': 24.5, 'radius_m': 1000,
           'is_active': True, 'disabled_at': None, 'notes': 'secret notes', 'created_at': T, 'updated_at': T}
    row.update(over)
    return row


@pytest.fixture()
def zone_calls(monkeypatch):
    seen = {'evaluate': 0, 'notified': []}

    class _Alarm:
        def request_evaluation(self):
            seen['evaluate'] += 1

    async def _notify(conn, channel, payload):
        seen['notified'].append((channel, payload))
    monkeypatch.setattr(fire_router, 'fire_alarm', _Alarm())
    monkeypatch.setattr(fire_router, 'notify', _notify)
    return seen


def _stub(monkeypatch, name, result):
    captured = {}

    async def fake(*args):
        captured['args'] = args
        if isinstance(result, Exception):
            raise result
        return result
    monkeypatch.setattr(repository, name, fake)
    return captured


EDIT = {'label': 'L', 'latitude': 42.5, 'longitude': 24.5, 'radius_m': 800, 'expected_updated_at': T.isoformat()}
VERSION = {'expected_updated_at': T.isoformat()}
ZONE_WRITES = [('put', '', EDIT), ('post', '/disable', VERSION), ('post', '/enable', VERSION)]


def test_zone_out_carries_updated_at():
    from backend.fire.models import zone_out
    assert zone_out(_zone())['updated_at'] == T.isoformat()


def test_edit_passes_the_version_and_never_is_active(client, monkeypatch, zone_calls):
    captured = _stub(monkeypatch, 'update_zone', _zone(radius_m=800))
    zid = uuid.uuid4()
    resp = client.put(f'/api/fire/suppression-zones/{zid}', json=EDIT)
    assert resp.status_code == 200 and resp.json()['updated_at'] == T.isoformat()
    _, zone_id, data, expected, _user = captured['args']
    assert zone_id == str(zid) and expected == T and 'is_active' not in data
    assert zone_calls['evaluate'] == 1 and zone_calls['notified'] == [('fire_zones_updated', {})]


@pytest.mark.parametrize('extra', [{'is_active': True}, {'is_active': False}])
def test_edit_with_is_active_is_422(client, monkeypatch, zone_calls, extra):
    _stub(monkeypatch, 'update_zone', _zone())
    assert client.put(f'/api/fire/suppression-zones/{uuid.uuid4()}', json={**EDIT, **extra}).status_code == 422
    assert zone_calls['evaluate'] == 0


@pytest.mark.parametrize('bad', [None, 'yesterday', '2026-10-04T10:00:00'])  # missing, junk, timezone-less
def test_edit_needs_an_aware_version(client, monkeypatch, zone_calls, bad):
    _stub(monkeypatch, 'update_zone', _zone())
    body = {k: v for k, v in EDIT.items() if k != 'expected_updated_at'}
    if bad is not None:
        body['expected_updated_at'] = bad
    assert client.put(f'/api/fire/suppression-zones/{uuid.uuid4()}', json=body).status_code == 422


@pytest.mark.parametrize('method, suffix, body', ZONE_WRITES)
def test_stale_zone_is_409_and_nothing_is_announced(client, monkeypatch, zone_calls, method, suffix, body):
    _stub(monkeypatch, 'update_zone', repository.ZoneStaleError('x'))
    _stub(monkeypatch, 'set_zone_active', repository.ZoneStaleError('x'))
    resp = getattr(client, method)(f'/api/fire/suppression-zones/{uuid.uuid4()}{suffix}', json=body)
    assert resp.status_code == 409 and resp.json() == {'detail': 'zone_stale'}
    assert zone_calls['evaluate'] == 0 and zone_calls['notified'] == []


@pytest.mark.parametrize('method, suffix, body', ZONE_WRITES)
def test_unknown_zone_is_404(client, monkeypatch, zone_calls, method, suffix, body):
    _stub(monkeypatch, 'update_zone', None)
    _stub(monkeypatch, 'set_zone_active', None)
    assert getattr(client, method)(f'/api/fire/suppression-zones/{uuid.uuid4()}{suffix}', json=body).status_code == 404
    assert zone_calls['evaluate'] == 0


@pytest.mark.parametrize('suffix, active', [('/disable', False), ('/enable', True)])
def test_enable_disable_flip_activation_with_the_version(client, monkeypatch, zone_calls, suffix, active):
    captured = _stub(monkeypatch, 'set_zone_active', _zone(is_active=active))
    resp = client.post(f'/api/fire/suppression-zones/{uuid.uuid4()}{suffix}', json=VERSION)
    assert resp.status_code == 200 and resp.json()['is_active'] is active
    assert captured['args'][2] is active and captured['args'][3] == T
    assert zone_calls['evaluate'] == 1 and zone_calls['notified'] == [('fire_zones_updated', {})]


def test_delete_alias_and_create_also_broadcast(client, monkeypatch, zone_calls):
    _stub(monkeypatch, 'disable_zone', _zone(is_active=False))
    assert client.delete(f'/api/fire/suppression-zones/{uuid.uuid4()}').status_code == 200
    _stub(monkeypatch, 'create_zone', _zone())
    assert client.post('/api/fire/suppression-zones',
                       json={'label': 'x', 'latitude': 42.5, 'longitude': 24.5}).status_code == 201
    assert zone_calls['evaluate'] == 2
    assert zone_calls['notified'] == [('fire_zones_updated', {})] * 2


@pytest.mark.parametrize('method, suffix, body', ZONE_WRITES)
def test_zone_edits_need_admin(client, test_app, monkeypatch, zone_calls, viewer_user, method, suffix, body):
    _stub(monkeypatch, 'update_zone', _zone())
    _stub(monkeypatch, 'set_zone_active', _zone())
    test_app.dependency_overrides[get_current_user] = lambda: viewer_user
    assert getattr(client, method)(f'/api/fire/suppression-zones/{uuid.uuid4()}{suffix}', json=body).status_code == 403


def test_zone_write_audit_line_has_ids_only(client, monkeypatch, zone_calls, admin_user, caplog):
    _stub(monkeypatch, 'update_zone', _zone())
    zid = uuid.uuid4()
    with caplog.at_level(logging.INFO, logger='backend.modules.fire.http'):
        client.put(f'/api/fire/suppression-zones/{zid}', json=EDIT)
    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith('fire zone')]
    assert len(lines) == 1
    assert str(zid) in lines[0] and admin_user['id'] in lines[0] and 'is_active=True' in lines[0]
    assert 'Secret label' not in lines[0] and 'secret notes' not in lines[0]


def test_zones_channel_is_forwarded():
    assert 'fire_zones_updated' in ws.FORWARDED_CHANNELS


class _FakeConn:
    """Records queries; the fetchrow() result and the existence probe are scripted."""

    def __init__(self, row, exists):
        self.row, self.exists, self.sql = row, exists, []

    async def fetchrow(self, sql, *args):
        self.sql.append((sql, args))
        return self.row

    async def fetchval(self, sql, *args):
        self.sql.append((sql, args))
        return 1 if self.exists else None


ZONE_DATA = {'label': 'a', 'latitude': 1.0, 'longitude': 2.0, 'radius_m': 100, 'notes': None}


@pytest.mark.asyncio
async def test_repository_update_is_guarded_by_updated_at_and_leaves_activation_alone():
    conn = _FakeConn({'id': 1}, True)
    await repository.update_zone(conn, str(uuid.uuid4()), ZONE_DATA, T, 'u')
    sql, args = conn.sql[0]
    assert 'updated_at = $2' in sql and 'is_active' not in sql and args[1] == T


@pytest.mark.asyncio
@pytest.mark.parametrize('exists', [True, False], ids=['stale', 'missing'])
async def test_repository_write_distinguishes_stale_from_missing(exists):
    conn = _FakeConn(None, exists)
    calls = (lambda: repository.update_zone(conn, str(uuid.uuid4()), ZONE_DATA, T, 'u'),
             lambda: repository.set_zone_active(conn, str(uuid.uuid4()), False, T, 'u'))
    for call in calls:
        if exists:
            with pytest.raises(repository.ZoneStaleError):
                await call()
        else:
            assert await call() is None


# -- item 3: login always runs bcrypt -----------------------------------------------------------------------------

@pytest.fixture()
def login(monkeypatch, mock_conn):
    app = FastAPI()
    app.include_router(auth_router.router)

    async def _gc():
        yield mock_conn
    app.dependency_overrides[get_conn] = _gc
    monkeypatch.setattr(settings, 'login_roles', 'admin')
    seen = []
    real = auth_router.verify_password

    def spy(plain, hashed):
        seen.append(hashed)
        return real(plain, hashed)
    monkeypatch.setattr(auth_router, 'verify_password', spy)
    return TestClient(app), mock_conn, seen


def _user(role='admin', active=True, password='secret', no_hash=None):
    return {'id': uuid.uuid4(), 'role': role, 'is_active': active,
            'password_hash': no_hash if no_hash is not None else hash_password(password)}


@pytest.mark.parametrize('row', [None, _user(active=False), _user(role='rescuer'), _user(no_hash=''),
                                 _user(no_hash=None)],
                         ids=['unknown', 'inactive', 'role-not-allowed', 'empty-hash', 'real-hash'])
def test_login_runs_bcrypt_for_every_refusal(login, row):
    client, conn, seen = login
    if row is not None and row['password_hash'] and row['is_active'] and row['role'] == 'admin':
        row = {**row, 'password_hash': hash_password('other')}      # right account, wrong password
    conn.fetchrow = AsyncMock(return_value=row)
    resp = client.post('/api/auth/login', data={'username': 'u', 'password': 'secret'})
    assert resp.status_code == 401 and resp.json() == {'detail': 'Invalid credentials'}
    assert len(seen) == 1
    if row is None or not row['password_hash']:
        assert seen[0] == auth_router._DUMMY_HASH


def test_dummy_hash_is_a_real_bcrypt_hash():
    assert auth_router._DUMMY_HASH.startswith('$2')
    assert auth_module.verify_password('x', auth_router._DUMMY_HASH) is False


def test_login_right_password_still_works(login):
    client, conn, _ = login
    conn.fetchrow = AsyncMock(return_value=_user())
    assert client.post('/api/auth/login', data={'username': 'u', 'password': 'secret'}).status_code == 200


def test_login_with_a_password_over_72_bytes_is_401_not_500(login):
    client, conn, _ = login
    conn.fetchrow = AsyncMock(return_value=_user())
    assert client.post('/api/auth/login', data={'username': 'u', 'password': 'x' * 100}).status_code == 401


# -- item 4: Bearer must be an access token of an allowed role ----------------------------------------------------

def _conn_with(role='admin', active=True):
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value={'id': 'x', 'username': 'u', 'full_name': 'U', 'role': role,
                                            'is_active': active})
    return conn


@pytest.mark.asyncio
async def test_access_token_is_accepted(monkeypatch):
    monkeypatch.setattr(settings, 'login_roles', 'admin')
    user = await get_current_user(create_access_token('x', 'admin'), _conn_with())
    assert user['role'] == 'admin'


@pytest.mark.asyncio
async def test_refresh_token_is_not_a_bearer_token(monkeypatch):
    monkeypatch.setattr(settings, 'login_roles', 'admin')
    with pytest.raises(HTTPException) as err:
        await get_current_user(create_refresh_token('x', 'admin'), _conn_with())
    assert err.value.status_code == 401 and err.value.detail == 'Invalid or expired token'


@pytest.mark.asyncio
async def test_token_without_typ_is_refused(monkeypatch):
    monkeypatch.setattr(settings, 'login_roles', 'admin')
    legacy = jwt.encode({'sub': 'x', 'role': 'admin', 'exp': datetime.now(timezone.utc) + timedelta(hours=1)},
                        settings.secret_key, algorithm=auth_module.ALGORITHM)
    with pytest.raises(HTTPException) as err:
        await get_current_user(legacy, _conn_with())
    assert err.value.status_code == 401


@pytest.mark.asyncio
async def test_role_outside_login_roles_has_no_session(monkeypatch):
    monkeypatch.setattr(settings, 'login_roles', 'admin')
    with pytest.raises(HTTPException) as err:
        await get_current_user(create_access_token('x', 'rescuer'), _conn_with(role='rescuer'))
    assert err.value.status_code == 401 and err.value.detail == 'Invalid or expired token'
    monkeypatch.setattr(settings, 'login_roles', 'admin,rescuer')
    user = await get_current_user(create_access_token('x', 'rescuer'), _conn_with(role='rescuer'))
    assert user['role'] == 'rescuer'


def test_refresh_token_as_bearer_over_http_is_401(monkeypatch):
    from backend.main import app
    monkeypatch.setattr(settings, 'login_roles', 'admin')
    conn = _conn_with()
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchval = AsyncMock(return_value=0)

    async def _gc():
        yield conn
    app.dependency_overrides[get_conn] = _gc
    try:
        resp = TestClient(app).get('/api/fire/alerts',
                                   headers={'Authorization': f'Bearer {create_refresh_token("x", "admin")}'})
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.clear()


# -- item 5: B49 handler, NaN / Infinity / bytes ------------------------------------------------------------------

@pytest.fixture()
def real_app_client(mock_conn, admin_user):
    from backend.main import app

    async def _gc():
        yield mock_conn

    async def _u():
        return admin_user
    app.dependency_overrides[get_conn] = _gc
    app.dependency_overrides[get_current_user] = _u
    yield TestClient(app, raise_server_exceptions=True)
    app.dependency_overrides.clear()


@pytest.mark.parametrize('body', [
    '{"latitude": NaN, "longitude": 24.5}',
    '{"latitude": 42.5, "longitude": Infinity}',
    '{"latitude": -Infinity, "longitude": 24.5}'])
def test_non_finite_floats_are_422_not_500(real_app_client, body):
    resp = real_app_client.post('/api/fire/field-reports', content=body, headers=HEADERS)
    assert resp.status_code == 422
    assert resp.json()['detail'][0]['input'] is None


def test_non_finite_radius_is_422(real_app_client):
    resp = real_app_client.post('/api/fire/suppression-zones', headers=HEADERS,
                                content='{"label": "x", "latitude": 42, "longitude": 24, "radius_m": NaN}')
    assert resp.status_code == 422


def test_non_utf8_body_is_422_not_500(real_app_client):
    resp = real_app_client.post('/api/fire/field-reports', content=b'\xff\xfe\xfa',
                                headers={'Content-Type': 'text/plain'})
    assert resp.status_code == 422
    resp.content.decode('ascii')


def test_json_safe_handles_bytes_floats_and_tuples():
    from backend.main import _json_safe
    assert _json_safe({'a': b'\xff', 'b': float('nan'), 'c': (1.5, float('inf')), 'd': 'x'}) == {
        'a': '\\xff', 'b': None, 'c': [1.5, None], 'd': 'x'}


# -- items 6 and 7: SQL shape (behaviour is in the db tests) ------------------------------------------------------

@pytest.mark.asyncio
async def test_dismiss_with_notes_records_the_author_without_notes_changes_nothing():
    conn = _FakeConn({'id': 1}, True)
    await repository.dismiss_hotspot(conn, str(uuid.uuid4()), 'u', 'text')
    sql, args = conn.sql[0]
    assert 'CASE WHEN $3::text IS NOT NULL THEN NOW()' in sql and 'CASE WHEN $3::text IS NOT NULL THEN $2::uuid' in sql
    assert args[2] == 'text'


@pytest.mark.asyncio
async def test_latest_device_position_selects_gnss_valid():
    conn = _FakeConn({'latitude': 1.0, 'longitude': 2.0, 'gnss_valid': False}, True)
    row = await repository.latest_device_position(conn, str(uuid.uuid4()))
    assert 'gnss_valid' in conn.sql[0][0] and row['gnss_valid'] is False
