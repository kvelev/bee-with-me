"""T502: `fire` is a backend module (backend/modules/fire/); the old import paths stay as aliases until step 5."""
import ast
import importlib
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.tests.architecture.rules import effective_routes

REPO = Path(__file__).resolve().parents[4]
FIRE = REPO / 'backend' / 'modules' / 'fire'

pytestmark = pytest.mark.Trait("Task", "T502")

NEW = 'backend.modules.fire'
PAIRS = [
    ('backend.fire.models', f'{NEW}.domain.models'),
    ('backend.fire.parse', f'{NEW}.domain.parse'),
    ('backend.fire.proximity', f'{NEW}.domain.proximity'),
    ('backend.fire.h3index', f'{NEW}.domain.h3index'),
    ('backend.fire.repository', f'{NEW}.infrastructure.repository'),
    ('backend.fire.sources', f'{NEW}.infrastructure.sources'),
    ('backend.fire.poller', f'{NEW}.infrastructure.poller'),
    ('backend.fire.service', f'{NEW}.infrastructure.service'),
    ('backend.routers.fire', f'{NEW}.http'),
]

# taken from app.openapi() on develop (54719af) before the move
OPERATION_IDS = {
    'hotspots_api_fire_hotspots_get',
    'burnt_areas_api_fire_burnt_areas_get',
    'status_api_fire_status_get',
    'list_alerts_api_fire_alerts_get',
    'acknowledge_all_api_fire_alerts_acknowledge_all_post',
    'acknowledge_api_fire_alerts__alert_id__acknowledge_post',
    'dismiss_hotspot_api_fire_hotspots__hotspot_id__dismiss_post',
    'create_field_report_api_fire_field_reports_post',
    'extinguish_field_report_api_fire_field_reports__hotspot_id__extinguish_post',
    'list_zones_api_fire_suppression_zones_get',
    'create_zone_api_fire_suppression_zones_post',
    'update_zone_api_fire_suppression_zones__zone_id__put',
    'disable_zone_api_fire_suppression_zones__zone_id__delete',
    'disable_zone_versioned_api_fire_suppression_zones__zone_id__disable_post',
    'enable_zone_api_fire_suppression_zones__zone_id__enable_post',
}


def _run(code: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, '-c', code], cwd=REPO, capture_output=True, text=True, timeout=120)


@pytest.mark.parametrize('old,new', PAIRS)
def test_old_paths_are_the_new_modules(old, new):
    assert importlib.import_module(old) is importlib.import_module(new)


def test_from_the_old_package_gives_the_new_module():
    from backend.fire import repository as via_pkg
    import backend.modules.fire.infrastructure.repository as new
    assert via_pkg is new
    from backend.routers import fire as router_via_pkg
    import backend.modules.fire.http as new_http
    assert router_via_pkg is new_http


@pytest.mark.parametrize('old,new', PAIRS)
def test_importing_an_old_path_first_works(old, new):
    res = _run(f'import {old} as m; print(m.__name__)')
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == new


def test_state_is_shared_through_the_alias():
    import backend.fire.poller as old_poller
    import backend.fire.service as old_service
    import backend.modules.fire.infrastructure.poller as new_poller
    import backend.modules.fire.infrastructure.service as new_service
    assert old_poller.FEEDS is new_poller.FEEDS
    assert old_service.service is new_service.service


def test_manifest():
    from backend.modules import MODULES
    import backend.modules.fire.http as http
    from backend.modules.fire.module import manifest
    assert manifest.name == 'fire'
    assert set(manifest.owns_tables) == {'fire_hotspots', 'fire_burnt_areas', 'fire_alerts', 'fire_suppression_zones'}
    assert set(manifest.live_messages) == {'fire_data_updated', 'fire_alert', 'fire_alert_repeat', 'fire_alert_updated',
                                           'fire_zones_updated'}
    assert manifest.router is http.router
    assert manifest.public_routes == ()
    assert [t.__name__ for t in manifest.tasks] == ['poll_feeds', 'alarm_loop', 'cleanup_fire_data']   # T503
    assert manifest in MODULES
    names = [m.name for m in MODULES]
    assert names.index('fire') < names.index('settings')


def test_fire_routes_are_served_once_by_the_real_app():
    from backend.main import app
    from backend.modules.fire import http
    routes = effective_routes(app.routes)
    mine = effective_routes(http.router.routes)
    assert len(mine) == 15
    for r in mine:
        hits = [x for x in routes if x.path == r.path and x.methods == r.methods]
        assert len(hits) == 1, (r.path, r.methods, len(hits))


def test_fire_routes_keep_their_place():
    from backend.main import app
    paths = [r.path for r in effective_routes(app.routes)]
    first_fire = next(i for i, p in enumerate(paths) if p.startswith('/api/fire'))
    last_export = max(i for i, p in enumerate(paths) if p.startswith('/api/export'))
    first_settings = next(i for i, p in enumerate(paths) if p.startswith('/api/settings'))
    assert last_export < first_fire < first_settings


def test_every_fire_route_needs_a_login():
    from backend.main import app
    from backend.modules.fire import http
    client = TestClient(app)        # no `with`: the lifespan (database, reader) does not start
    seen = 0
    for r in effective_routes(http.router.routes):
        path = r.path.replace('{alert_id}', '1').replace('{hotspot_id}', '1').replace('{zone_id}', '1')
        for method in r.methods:
            assert client.request(method, path).status_code == 401, (method, r.path)
            seen += 1
    assert seen == 15


def test_openapi_operation_ids_are_unchanged():
    from backend.main import app
    ids = [op.get('operationId') for path, item in app.openapi()['paths'].items() if path.startswith('/api/fire')
           for op in item.values()]
    assert len(ids) == 15 and set(ids) == OPERATION_IDS


def test_main_no_longer_mounts_the_fire_router():
    text = (REPO / 'backend' / 'main.py').read_text(encoding='utf-8')
    assert 'fire.router' not in text


def test_domain_is_pure():
    banned = {'asyncpg', 'httpx', 'fastapi'}
    files = sorted((FIRE / 'domain').glob('*.py'))
    assert {f.name for f in files} >= {'models.py', 'parse.py', 'proximity.py', 'h3index.py'}
    for f in files:
        for node in ast.walk(ast.parse(f.read_text(encoding='utf-8'))):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names = [node.module or '']
            else:
                continue
            for n in names:
                assert n.split('.')[0] not in banned, (f.name, n)
