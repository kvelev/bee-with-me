"""T402: `settings` is the first vertical-slice module (backend/modules/settings/)."""
import ast
import logging
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from backend.tests.architecture.rules import effective_routes

REPO = Path(__file__).resolve().parents[4]
DOMAIN_MODELS = REPO / 'backend' / 'modules' / 'settings' / 'domain' / 'models.py'

ROW = {'id': 1, 'hq_latitude': None, 'hq_longitude': None, 'is_hq_alarm_enabled': True,
       'is_rescuer_alarm_enabled': True, 'hq_radius_m': 10000, 'rescuer_radius_m': 3000,
       'alarm_max_age_hours': 24, 'repeat_minutes': 5, 'is_rescuer_photo_on_map_enabled': True,
       'updated_by': None,
       'updated_at': datetime(2026, 10, 2, tzinfo=timezone.utc)}
BODY = {k: ROW[k] for k in ('hq_latitude', 'hq_longitude', 'is_hq_alarm_enabled', 'is_rescuer_alarm_enabled',
                            'hq_radius_m', 'rescuer_radius_m', 'alarm_max_age_hours', 'repeat_minutes',
                            'is_rescuer_photo_on_map_enabled')}
BODY = {**BODY, 'expected_updated_at': ROW['updated_at'].isoformat()}
HQ = {'hq_latitude': 42.5, 'hq_longitude': 24.5}
HQ_ROW = {**ROW, **HQ}

pytestmark = pytest.mark.Trait("Task", "T402")


def _run(code: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, '-c', code], cwd=REPO, capture_output=True, text=True, timeout=120)


def test_old_router_path_is_the_module_http():
    import backend.modules.settings.http as new
    import backend.routers.settings as old
    from backend.routers import settings as via_pkg
    assert old is new
    assert via_pkg is new


def test_importing_the_old_path_first_works():
    res = _run('import backend.routers.settings as s; print(s.__name__)')
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == 'backend.modules.settings.http'


def test_manifest():
    from backend.modules import MODULES
    import backend.modules.settings.http as http
    from backend.modules.settings.module import manifest
    assert manifest.name == 'settings'
    assert manifest.owns_tables == ('settings',)
    assert manifest.depends_on == ()
    assert manifest.tasks == () and manifest.live_messages == ()
    assert manifest.public_routes == ()       # settings has nothing anonymous (decision of Kiril)
    assert manifest.router is http.router
    assert manifest in MODULES
    import backend.modules.settings.http as h       # the package is still the package, not the manifest
    assert h is http


def test_importing_the_api_does_not_import_http():
    res = _run("import sys, backend.modules.settings.api; "
               "print('backend.modules.settings.http' in sys.modules, 'backend.fire.service' in sys.modules)")
    assert res.returncode == 0, res.stderr
    assert res.stdout.split() == ['False', 'False']


def test_main_no_longer_wires_settings():
    text = (REPO / 'backend' / 'main.py').read_text(encoding='utf-8')
    assert 'settings_router' not in text and 'after_change' not in text


def test_settings_routes_are_served_once_by_the_real_app():
    from backend.main import app
    routes = effective_routes(app.routes)
    for path, method in [('/api/settings', 'GET'), ('/api/settings', 'PUT'),
                         ('/api/settings/hq', 'PUT'), ('/api/settings/hq-initial', 'PUT')]:
        hits = [r for r in routes if r.path == path and method in r.methods]
        assert len(hits) == 1, (path, method, len(hits))


def test_settings_routes_keep_their_place():
    from backend.main import app
    paths = [r.path for r in effective_routes(app.routes)]
    first_settings = paths.index('/api/settings')
    last_fire = max(i for i, p in enumerate(paths) if p.startswith('/api/fire'))
    assert last_fire < first_settings < paths.index('/ws')


def test_openapi_operation_ids_are_unchanged():
    from backend.main import app
    paths = app.openapi()['paths']
    ids = {op['operationId'] for p in ('/api/settings', '/api/settings/hq', '/api/settings/hq-initial')
           for op in paths[p].values()}
    assert ids >= {'get_settings_api_settings_get', 'put_settings_api_settings_put',
                   'put_hq_api_settings_hq_put', 'put_hq_initial_api_settings_hq_initial_put'}
    for p, verb in [('/api/settings', 'get'), ('/api/settings', 'put'),
                    ('/api/settings/hq', 'put'), ('/api/settings/hq-initial', 'put')]:
        ref = paths[p][verb]['responses']['200']['content']['application/json']['schema']['$ref']
        assert ref.endswith('/SettingsOut')


def _count_evaluations(monkeypatch) -> list:
    from backend.fire import service as fire_service
    calls: list = []
    monkeypatch.setattr(fire_service.service, 'request_evaluation', lambda: calls.append(1))
    return calls


def test_a_saved_change_asks_fire_to_re_evaluate(client, mock_conn, monkeypatch):
    calls = _count_evaluations(monkeypatch)
    mock_conn.fetchrow = AsyncMock(return_value=HQ_ROW)
    assert client.put('/api/settings/hq', json=HQ).status_code == 200
    assert calls == [1]
    assert client.put('/api/settings', json={**BODY, **HQ}).status_code == 200
    assert calls == [1, 1]
    assert client.put('/api/settings/hq-initial', json=HQ).status_code == 200
    assert calls == [1, 1, 1]


def test_fire_is_asked_after_the_transaction_and_the_broadcast(client, mock_conn, monkeypatch):
    from backend.fire import service as fire_service
    import backend.modules.settings.http as http
    order: list[str] = []

    async def _commit(*_a):
        order.append('commit')
        return False

    async def _notify(conn, ids):
        order.append('notify')

    mock_conn.transaction.return_value.__aexit__ = AsyncMock(side_effect=_commit)
    monkeypatch.setattr(http, 'notify_alerts_updated', _notify)
    monkeypatch.setattr(fire_service.service, 'request_evaluation', lambda: order.append('evaluate'))
    mock_conn.fetchrow = AsyncMock(return_value=ROW)
    monkeypatch.setattr(http.fire_repository, 'resolve_hq_alerts', AsyncMock(return_value=['a1']))
    res = client.put('/api/settings/hq', json={'hq_latitude': None, 'hq_longitude': None})
    assert res.status_code == 200
    assert order == ['commit', 'notify', 'evaluate']


def test_publish_failure_does_not_fail_the_request(client, mock_conn, monkeypatch, caplog):
    from backend.fire import service as fire_service

    def _boom():
        raise RuntimeError('boom')

    monkeypatch.setattr(fire_service.service, 'request_evaluation', _boom)
    mock_conn.fetchrow = AsyncMock(return_value=HQ_ROW)
    with caplog.at_level(logging.ERROR, logger='backend.modules.settings.infrastructure.publisher'):
        res = client.put('/api/settings/hq', json=HQ)
    assert res.status_code == 200
    records = [r for r in caplog.records if r.name == 'backend.modules.settings.infrastructure.publisher']
    assert len(records) == 1 and 'SettingsChanged' in records[0].getMessage()


def test_a_refused_change_publishes_nothing(client, mock_conn, monkeypatch):
    calls = _count_evaluations(monkeypatch)
    mock_conn.fetchrow = AsyncMock(return_value=None)
    mock_conn.fetchval = AsyncMock(return_value=1)
    res = client.put('/api/settings', json=BODY)
    assert res.status_code == 409 and res.json()['detail'] == 'settings_stale'
    assert client.put('/api/settings', json={**BODY, 'hq_radius_m': 99}).status_code == 422
    assert calls == []


def test_domain_models_do_not_import_the_web_or_the_database():
    tree = ast.parse(DOMAIN_MODELS.read_text(encoding='utf-8'))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split('.')[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            imported.add((node.module or '').split('.')[0])
        elif isinstance(node, ast.ImportFrom):
            imported.add('<relative>')
    assert imported <= {'datetime', 'typing', 'pydantic'}, imported
