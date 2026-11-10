"""T307: request-ID middleware and correlated log lines (pure ASGI, no DB)."""
import asyncio
import logging
import re

import httpx
import pytest
from fastapi import FastAPI
from fastapi import WebSocket
from starlette.testclient import TestClient

from backend.core.request_id import (
    REQUEST_ID_HEADER,
    RequestIdLogFilter,
    RequestIdMiddleware,
    accept_request_id,
    get_request_id,
    use_request_id,
)

log = logging.getLogger('t307.test')


def _make_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)

    @app.get('/ping')
    async def ping():
        log.info('ping handled')
        return {'id': get_request_id()}

    @app.get('/slow')
    async def slow():
        first = get_request_id()
        await asyncio.sleep(0)
        return {'before': first, 'after': get_request_id()}

    @app.get('/needs-int/{n}')
    async def needs_int(n: int):
        return {'n': n}

    @app.get('/boom')
    async def boom():
        raise RuntimeError('boom')

    @app.websocket('/ws-echo')
    async def ws_echo(ws: WebSocket):
        await ws.accept()
        await ws.send_text(await ws.receive_text())
        await ws.close()

    return app


@pytest.fixture
def app():
    return _make_app()


@pytest.mark.Trait("Task", "T307")
def test_valid_incoming_id_is_echoed_and_logged(app, caplog):
    caplog.handler.addFilter(RequestIdLogFilter())
    caplog.set_level(logging.INFO, logger='t307.test')
    with TestClient(app) as client:
        r = client.get('/ping', headers={REQUEST_ID_HEADER: 'abc-123'})
    assert r.headers[REQUEST_ID_HEADER] == 'abc-123'
    assert r.json() == {'id': 'abc-123'}
    recs = [x for x in caplog.records if x.name == 't307.test']
    assert recs and recs[0].request_id == 'abc-123'


@pytest.mark.Trait("Task", "T307")
def test_missing_id_is_generated(app):
    with TestClient(app) as client:
        r = client.get('/ping')
    assert re.fullmatch(r'[0-9a-f]{32}', r.headers[REQUEST_ID_HEADER])
    assert r.json()['id'] == r.headers[REQUEST_ID_HEADER]


@pytest.mark.Trait("Task", "T307")
@pytest.mark.parametrize('bad', ['a\r\nb', 'x' * 65, 'has space', 'ok\n', ''])
def test_invalid_ids_are_replaced(bad):
    out = accept_request_id(bad)
    assert out != bad
    assert re.fullmatch(r'[0-9a-f]{32}', out)


@pytest.mark.Trait("Task", "T307")
def test_invalid_header_on_the_wire_is_replaced(app):
    with TestClient(app) as client:
        r = client.get('/ping', headers={REQUEST_ID_HEADER: 'has space'})
    assert re.fullmatch(r'[0-9a-f]{32}', r.headers[REQUEST_ID_HEADER])


@pytest.mark.Trait("Task", "T307")
def test_accepts_none_and_max_length():
    assert re.fullmatch(r'[0-9a-f]{32}', accept_request_id(None))
    assert accept_request_id('a' * 64) == 'a' * 64


@pytest.mark.Trait("Task", "T307")
def test_header_present_on_404_and_422(app):
    with TestClient(app) as client:
        r404 = client.get('/nope')
        r422 = client.get('/needs-int/abc')
    assert r404.status_code == 404 and REQUEST_ID_HEADER in r404.headers
    assert r422.status_code == 422 and REQUEST_ID_HEADER in r422.headers


@pytest.mark.Trait("Task", "T307")
def test_unhandled_exception_response_has_no_header(app):
    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.get('/boom')
    assert r.status_code == 500
    assert REQUEST_ID_HEADER not in r.headers


@pytest.mark.Trait("Task", "T307")
@pytest.mark.asyncio
async def test_concurrent_requests_do_not_share_ids(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url='http://t') as client:
        ids = [f'req-{i}' for i in range(20)]
        resps = await asyncio.gather(
            *[client.get('/slow', headers={REQUEST_ID_HEADER: i}) for i in ids]
        )
    for i, r in zip(ids, resps):
        assert r.headers[REQUEST_ID_HEADER] == i
        assert r.json() == {'before': i, 'after': i}


@pytest.mark.Trait("Task", "T307")
def test_websocket_connection_still_works(app):
    with TestClient(app) as client:
        with client.websocket_connect('/ws-echo') as ws:
            ws.send_text('hi')
            assert ws.receive_text() == 'hi'


@pytest.mark.Trait("Task", "T307")
def test_filter_defaults_to_dash_outside_a_request():
    rec = logging.LogRecord('n', logging.INFO, __file__, 1, 'm', None, None)
    assert RequestIdLogFilter().filter(rec) is True
    assert rec.request_id == '-'


@pytest.mark.Trait("Task", "T307")
def test_var_is_reset_after_request(app):
    with TestClient(app) as client:
        client.get('/ping', headers={REQUEST_ID_HEADER: 'abc'})
    assert get_request_id() == '-'


@pytest.mark.Trait("Task", "T307")
def test_use_request_id_sets_and_restores():
    with use_request_id('outer'):
        assert get_request_id() == 'outer'
        with use_request_id():
            inner = get_request_id()
            assert re.fullmatch(r'[0-9a-f]{32}', inner)
        assert get_request_id() == 'outer'
    assert get_request_id() == '-'


@pytest.mark.Trait("Task", "T307")
def test_formatter_survives_a_record_without_request_id():
    from backend.core.request_id import make_log_formatter

    rec = logging.LogRecord('n', logging.INFO, __file__, 1, 'hello %s', ('x',), None)
    assert make_log_formatter().format(rec) == 'INFO:n:[-] hello x'


@pytest.mark.Trait("Task", "T307")
def test_main_registers_middleware_and_log_filter():
    from backend.main import app as main_app

    assert any(m.cls is RequestIdMiddleware for m in main_app.user_middleware)
    import backend.main as m

    assert any(isinstance(f, RequestIdLogFilter) for f in m._log_handler.filters)


@pytest.mark.Trait("Task", "T307")
def test_main_imports_and_logs_with_request_id_outside_pytest():
    """Clean interpreter (no pytest log handler on root), like uvicorn: basicConfig must work."""
    import subprocess
    import sys

    code = (
        "import logging, backend.main\n"
        "from backend.core.request_id import use_request_id\n"
        "with use_request_id('rid-1'):\n"
        "    logging.getLogger('probe').info('hello')\n"
        "logging.getLogger('probe').info('outside')\n"
    )
    r = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    assert 'INFO:probe:[rid-1] hello' in r.stderr
    assert 'INFO:probe:[-] outside' in r.stderr
