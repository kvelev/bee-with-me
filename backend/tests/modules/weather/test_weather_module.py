"""T520: `weather` is a backend module (backend/modules/weather/): the OpenWeatherMap proxy, no table."""
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.tests.architecture.rules import effective_routes

REPO = Path(__file__).resolve().parents[4]

pytestmark = pytest.mark.Trait("Task", "T520")

TILE = '/api/weather/tiles/{layer}/{z}/{x}/{y}.png'
CURRENT = '/api/weather/current'
BOX = '/api/weather/box'


def _run(code: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, '-c', code], cwd=REPO, capture_output=True, text=True, timeout=120)


def test_old_router_path_is_the_module_http():
    import backend.modules.weather.http as new
    import backend.routers.weather as old
    from backend.routers import weather as via_pkg
    assert old is new
    assert via_pkg is new


def test_importing_the_old_path_first_works():
    res = _run('import backend.routers.weather as w; print(w.__name__)')
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == 'backend.modules.weather.http'


def test_manifest():
    from backend.modules import MODULES
    import backend.modules.weather.http as http
    from backend.modules.weather.module import manifest
    assert manifest.name == 'weather'
    assert manifest.owns_tables == ()
    assert manifest.depends_on == ()
    assert manifest.tasks == () and manifest.live_messages == ()
    assert manifest.public_routes == ()
    assert manifest.router is http.router
    assert manifest in MODULES


def test_weather_routes_are_served_once_by_the_real_app():
    from backend.main import app
    routes = effective_routes(app.routes)
    for path in (TILE, CURRENT, BOX):
        hits = [r for r in routes if r.path == path and 'GET' in r.methods]
        assert len(hits) == 1, (path, len(hits))


def test_every_weather_route_needs_a_login():
    from backend.main import app
    client = TestClient(app)        # no `with`: the lifespan (database, reader) does not start
    for url in ('/api/weather/tiles/clouds_new/3/4/2.png', '/api/weather/current?lat=42.7&lon=23.3',
                '/api/weather/box?bbox=23,42,24,43&zoom=8'):
        assert client.get(url).status_code == 401, url


def test_the_appid_filter_is_installed_by_importing_the_module_list():
    res = _run("import logging; from backend.modules import MODULES; "
               "print(any(type(f).__name__ == '_RedactAppid' for f in logging.getLogger('httpx').filters))")
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == 'True'


def test_openapi_operation_ids_are_unchanged():
    from backend.main import app
    ids = {op.get('operationId') for path, item in app.openapi()['paths'].items() if path.startswith('/api/weather')
           for op in item.values()}
    assert ids == {'tile_api_weather_tiles__layer___z___x___y__png_get',
                   'current_api_weather_current_get', 'box_api_weather_box_get'}


def test_main_no_longer_mounts_the_weather_router():
    text = (REPO / 'backend' / 'main.py').read_text(encoding='utf-8')
    assert 'weather' not in text
