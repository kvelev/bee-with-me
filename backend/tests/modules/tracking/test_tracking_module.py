"""T540: `tracking` and `sos` are backend modules (HTTP side); `backend.routers.locations` is a named shim."""
import asyncio
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from backend.tests.architecture.rules import effective_routes

TESTS = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.Trait("Task", "T540")

FIVE = {
    ('/api/locations/live', 'GET'),
    ('/api/locations/sos', 'GET'),
    ('/api/locations/sos/{alert_id}/resolve', 'POST'),
    ('/api/locations/trail', 'GET'),
    ('/api/locations/{device_id}/history', 'GET'),
}


def test_manifest():
    from backend.modules import MODULES
    import backend.modules.tracking.http as http
    from backend.modules.tracking.module import manifest
    assert manifest.name == 'tracking'
    assert manifest.owns_tables == ('location_events', 'repeater_events')
    assert set(manifest.reads_tables) == {'devices', 'groups', 'sos_alerts', 'user_groups', 'users'}
    assert manifest.depends_on == ()
    assert manifest.live_messages == ('location_update',)
    assert manifest.public_routes == ()
    assert manifest.router is http.router
    assert manifest in MODULES


def test_the_shim_passes_on_the_module_functions():
    import backend.modules.sos.http as sos
    import backend.modules.tracking.http as tracking
    import backend.routers.locations as old
    for name in ('live_positions', 'location_trail', 'device_history', 'settings'):
        assert getattr(old, name) is getattr(tracking, name), name
    for name in ('open_sos_alerts', 'resolve_sos'):
        assert getattr(old, name) is getattr(sos, name), name


def test_the_shim_router_serves_the_five_routes():
    import backend.routers.locations as old
    pairs = {(r.path, m) for r in effective_routes(old.router.routes) for m in r.methods}
    assert pairs == FIVE


def test_no_test_patches_a_name_of_the_locations_shim():
    needles = ('setattr(' + 'locations', "'backend.routers." + "locations.")
    me = Path(__file__).resolve()
    offenders = [str(p) for p in TESTS.rglob('*.py')
                 if p.resolve() != me and any(n in p.read_text(encoding='utf-8') for n in needles)]
    assert offenders == []


def test_the_five_routes_are_served_once_by_the_real_app():
    from backend.main import app
    routes = [r for r in effective_routes(app.routes) if r.path.startswith('/api/locations')]
    pairs = [(r.path, m) for r in routes for m in r.methods]
    assert sorted(pairs) == sorted(FIVE)


def test_every_route_needs_a_login():
    from backend.main import app
    client = TestClient(app)        # no `with`: the lifespan does not start
    some = uuid.uuid4()
    for method, url in (('GET', '/api/locations/live'), ('GET', '/api/locations/sos'),
                        ('POST', f'/api/locations/sos/{some}/resolve'), ('GET', '/api/locations/trail'),
                        ('GET', f'/api/locations/{some}/history')):
        assert client.request(method, url).status_code == 401, (method, url)


def test_openapi_operation_ids_are_unchanged():
    from backend.main import app
    ids = {op.get('operationId') for path, item in app.openapi()['paths'].items()
           if path.startswith('/api/locations') for op in item.values()}
    assert ids == {
        'live_positions_api_locations_live_get',
        'open_sos_alerts_api_locations_sos_get',
        'resolve_sos_api_locations_sos__alert_id__resolve_post',
        'location_trail_api_locations_trail_get',
        'device_history_api_locations__device_id__history_get',
    }


def test_main_no_longer_mounts_the_locations_router():
    src = (Path(__file__).resolve().parents[4] / 'backend' / 'main.py').read_text(encoding='utf-8')
    assert 'locations.router' not in src
    assert 'locations' not in src.split('from .routers import', 1)[1].splitlines()[0]


def test_live_reads_the_freshness_horizon_from_the_settings(monkeypatch):
    import backend.modules.tracking.http as http
    monkeypatch.setattr(http.settings, 'live_position_max_age_hours', 7)
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=[])
    assert asyncio.run(http.live_positions(conn, None)) == []
    assert conn.fetch.await_args.args[1] == 7
