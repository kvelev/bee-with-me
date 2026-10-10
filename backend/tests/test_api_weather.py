"""
OpenWeatherMap proxy (routers/weather.py): the key is added server-side and never reaches the client.
"""

import httpx
import pytest

from backend.routers import weather

KEY = 'k-' + 'x' * 30


class _Upstream:
    """Stands in for httpx.AsyncClient; records requests and answers with a canned response."""
    calls: list = []
    response = httpx.Response(200, json={})

    def __init__(self, *a, **kw):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, params=None):
        _Upstream.calls.append((url, dict(params or {})))
        if isinstance(_Upstream.response, Exception):
            raise _Upstream.response
        return _Upstream.response


@pytest.fixture(autouse=True)
def upstream(monkeypatch):
    _Upstream.calls = []
    _Upstream.response = httpx.Response(200, json={})
    monkeypatch.setattr(weather.httpx, 'AsyncClient', _Upstream)
    monkeypatch.setattr(weather.settings, 'owm_api_key', KEY)
    weather._tile_cache.clear()
    return _Upstream


def test_requires_login(test_app):
    from fastapi.testclient import TestClient
    with TestClient(test_app) as c:
        assert c.get('/api/weather/current?lat=42&lon=23').status_code == 401
        assert c.get('/api/weather/tiles/clouds_new/3/4/2.png').status_code == 401


def test_current_adds_key_server_side(client, upstream):
    upstream.response = httpx.Response(200, json={'main': {'temp': 12}, 'name': 'Sofia'})
    r = client.get('/api/weather/current?lat=42.698123&lon=23.322987')
    assert r.status_code == 200 and r.json()['name'] == 'Sofia'
    url, params = upstream.calls[0]
    assert url.endswith('/data/2.5/weather')
    assert params == {'lat': 42.6981, 'lon': 23.323, 'units': 'metric', 'appid': KEY}
    assert KEY not in r.text


def test_tile_is_proxied_and_cached(client, upstream):
    upstream.response = httpx.Response(200, content=b'\x89PNG...')
    for _ in range(2):
        r = client.get('/api/weather/tiles/precipitation_new/5/17/11.png')
        assert r.status_code == 200 and r.content == b'\x89PNG...'
        assert r.headers['content-type'] == 'image/png'
    assert len(upstream.calls) == 1
    assert upstream.calls[0] == ('https://tile.openweathermap.org/map/precipitation_new/5/17/11.png', {'appid': KEY})


@pytest.mark.parametrize('path', [
    '/api/weather/tiles/evil_layer/3/1/1.png',   # not an allowed layer
    '/api/weather/tiles/clouds_new/3/8/1.png',   # x outside 2^z
])
def test_tile_rejects_unknown_layers_and_coordinates(client, upstream, path):
    assert client.get(path).status_code == 404
    assert upstream.calls == []


def test_box_plan_refusal_is_not_an_auth_error(client, upstream):
    upstream.response = httpx.Response(401, json={'cod': 401})
    r = client.get('/api/weather/box?bbox=22.10,41.20,28.60,44.20&zoom=7')
    assert r.status_code == 200 and r.json() == {'denied': True}
    assert upstream.calls[0][1]['bbox'] == '22.10,41.20,28.60,44.20,7'


def test_box_rejects_a_malformed_bbox(client, upstream):
    assert client.get('/api/weather/box?bbox=1,2,3&zoom=7').status_code == 422
    assert upstream.calls == []


def test_upstream_failure_is_502_without_leaking_the_key(client, upstream):
    upstream.response = httpx.ConnectError(f'boom https://api.openweathermap.org/?appid={KEY}')
    r = client.get('/api/weather/current?lat=42&lon=23')
    assert r.status_code == 502 and KEY not in r.text
    upstream.response = httpx.Response(500, text=f'error for {KEY}')
    r = client.get('/api/weather/current?lat=42&lon=23')
    assert r.status_code == 502 and KEY not in r.text


def test_no_key_configured_is_503(client, upstream, monkeypatch):
    monkeypatch.setattr(weather.settings, 'owm_api_key', '')
    assert client.get('/api/weather/current?lat=42&lon=23').status_code == 503
    assert upstream.calls == []


def test_old_vite_variable_name_still_configures_the_key(monkeypatch):
    from backend.config import Settings
    monkeypatch.delenv('OWM_API_KEY', raising=False)
    monkeypatch.setenv('VITE_OWM_API_KEY', 'legacy')
    assert Settings(_env_file=None).owm_api_key == 'legacy'
    monkeypatch.setenv('OWM_API_KEY', 'new')
    assert Settings(_env_file=None).owm_api_key == 'new'   # the new name wins when both are set


def test_httpx_request_log_lines_never_carry_the_key(caplog):
    import logging
    with caplog.at_level(logging.INFO, logger='httpx'):
        logging.getLogger('httpx').info('HTTP Request: %s %s "%s"', 'GET',
                                        f'https://api.openweathermap.org/data/2.5/weather?lat=1&appid={KEY}&units=metric',
                                        'HTTP/1.1 200 OK')
    assert KEY not in caplog.text
    assert 'appid=***&units=metric' in caplog.text
