"""T400: the kernel mounts routers and starts tasks from the module list; main.py reads it."""
import ast
import asyncio
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi import APIRouter, FastAPI, HTTPException

from backend.core.modules import (
    ModuleManifest,
    check_modules,
    include_module_routers,
    start_module_tasks,
    stop_module_tasks,
)

MAIN = Path(__file__).resolve().parents[3] / 'main.py'


def _router(path: str) -> APIRouter:
    r = APIRouter()

    @r.get(path)
    async def _handler():
        return {}

    return r


async def _deny():
    """Stands for get_current_user in the loader tests."""
    raise HTTPException(status_code=401)


def _paths(app: FastAPI) -> list[str]:
    # newer FastAPI keeps an included router as one lazy route object without a path: read the schema instead
    return list(app.openapi()['paths'])


@pytest.mark.Trait("Task", "T400")
def test_include_module_routers_mounts_in_list_order():
    app = FastAPI()
    include_module_routers(app, [ModuleManifest(name='alpha', router=_router('/a')),
                                 ModuleManifest(name='beta', router=_router('/b'))], auth=_deny)
    assert _paths(app)[-2:] == ['/a', '/b']


@pytest.mark.Trait("Task", "T400")
def test_a_manifest_without_router_is_skipped():
    app = FastAPI()
    before = list(app.routes)
    include_module_routers(app, [ModuleManifest(name='gamma')], auth=_deny)
    assert list(app.routes) == before


@pytest.mark.Trait("Task", "T400")
@pytest.mark.parametrize('modules', [
    [ModuleManifest(name='Bad', router=_router('/x'))],
    [ModuleManifest(name='alpha', router=_router('/a')), ModuleManifest(name='alpha', router=_router('/b'))],
], ids=['bad-name', 'duplicate'])
def test_include_module_routers_refuses_an_invalid_list(modules):
    app = FastAPI()
    before = list(app.routes)
    with pytest.raises(ValueError, match='invalid module list'):
        include_module_routers(app, modules, auth=_deny)
    assert list(app.routes) == before
    assert check_modules(modules)


@pytest.mark.Trait("Task", "T400")
def test_check_modules_is_empty_for_a_valid_list():
    assert check_modules([ModuleManifest(name='alpha'), ModuleManifest(name='beta')]) == []


@pytest.mark.Trait("Task", "T400")
@pytest.mark.asyncio
async def test_start_and_stop_module_tasks():
    release = asyncio.Event()

    async def boom():
        raise RuntimeError('x')

    async def ok():
        await release.wait()

    on_done = Mock()
    tasks = start_module_tasks([ModuleManifest(name='alpha', tasks=(boom, ok))], on_done)
    assert [t.get_name() for t in tasks] == ['alpha.boom', 'alpha.ok']
    await asyncio.wait([tasks[0]])
    await asyncio.sleep(0)
    assert on_done.call_count == 1
    assert on_done.call_args.args == (tasks[0], 'alpha.boom')

    await stop_module_tasks(tasks)
    assert all(t.done() for t in tasks)
    assert tasks[1].cancelled()
    assert [c.args[1] for c in on_done.call_args_list] == ['alpha.boom', 'alpha.ok']


@pytest.mark.Trait("Task", "T400")
def test_main_uses_the_loader():
    tree = ast.parse(MAIN.read_text(encoding='utf-8'))

    def call_name(node):
        f = node.func
        return f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None

    top = [n.value for n in tree.body if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)]
    assert any(call_name(c) == 'include_module_routers' and [getattr(a, 'id', None) for a in c.args] == ['app', 'MODULES']
               and {k.arg: getattr(k.value, 'id', None) for k in c.keywords} == {'auth': 'get_current_user'}
               for c in top)
    lifespan = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == 'lifespan')
    calls = {}
    for n in ast.walk(lifespan):
        if isinstance(n, ast.Call) and call_name(n):
            calls.setdefault(call_name(n), []).append(n.lineno)
    assert 'start_module_tasks' in calls
    assert min(calls['stop_module_tasks']) < min(calls['close_pool'])


@pytest.mark.Trait("Task", "T400")
def test_every_module_router_is_mounted_in_the_real_app():
    from backend.main import app
    from backend.modules import MODULES

    # schema paths: routes with include_in_schema=False are not seen here
    paths = app.openapi()['paths']
    for m in MODULES:
        if m.router is None:
            continue
        for r in m.router.routes:
            if getattr(r, 'include_in_schema', True):
                assert {x.lower() for x in r.methods} <= set(paths[r.path])


# ── auth by default (decision of Kiril): every module route is behind the auth dependency unless declared public ──

def _two_routes() -> APIRouter:
    r = APIRouter()

    @r.get('/pub')
    async def _pub():
        return {'ok': True}

    @r.get('/priv')
    async def _priv():
        return {'ok': True}

    return r


@pytest.mark.Trait("Task", "T402")
def test_the_loader_puts_the_auth_dependency_on_every_module_route():
    from fastapi.testclient import TestClient
    app = FastAPI()
    include_module_routers(app, [ModuleManifest(name='alpha', router=_two_routes())], auth=_deny)
    client = TestClient(app)
    assert client.get('/pub').status_code == 401
    assert client.get('/priv').status_code == 401


@pytest.mark.Trait("Task", "T402")
def test_a_declared_public_route_stays_anonymous_and_the_rest_is_guarded():
    from fastapi.testclient import TestClient
    app = FastAPI()
    include_module_routers(
        app, [ModuleManifest(name='alpha', router=_two_routes(), public_routes=(('GET', '/pub'),))], auth=_deny)
    client = TestClient(app)
    assert client.get('/pub').status_code == 200
    assert client.get('/priv').status_code == 401


@pytest.mark.Trait("Task", "T402")
@pytest.mark.parametrize('public', [
    (('GET', '/nope'),),            # not a route of this module: a typo must not pass quietly
    (('POST', '/pub'),),            # right path, wrong method
], ids=['unknown-path', 'wrong-method'])
def test_a_public_declaration_that_matches_no_route_refuses_the_list(public):
    app = FastAPI()
    before = list(app.routes)
    with pytest.raises(ValueError, match='invalid module list'):
        include_module_routers(
            app, [ModuleManifest(name='alpha', router=_two_routes(), public_routes=public)], auth=_deny)
    assert list(app.routes) == before


@pytest.mark.Trait("Task", "T402")
@pytest.mark.parametrize('public', [
    (('get', '/pub'),), (('GET', 'pub'),), (('GET',),), ('GET /pub',), (('GET', '/pub'), ('GET', '/pub')),
], ids=['lowercase-method', 'path-without-slash', 'one-item', 'a-string', 'twice'])
def test_validate_manifest_refuses_a_malformed_public_route(public):
    from backend.core.modules import validate_manifest
    assert validate_manifest(ModuleManifest(name='alpha', public_routes=public))


@pytest.mark.Trait("Task", "T402")
def test_a_module_route_needs_the_auth_argument():
    with pytest.raises(TypeError):
        include_module_routers(FastAPI(), [ModuleManifest(name='alpha', router=_two_routes())])   # type: ignore[call-arg]


@pytest.mark.Trait("Bug", "B94")
@pytest.mark.asyncio
async def test_start_module_tasks_names_a_task_without_a_name_attribute():
    import functools

    async def work(n):
        return n

    class Job:
        async def __call__(self):
            return None

    on_done = Mock()
    tasks = start_module_tasks(
        [ModuleManifest(name='alpha', tasks=(functools.partial(work, 1), Job()))], on_done)   # type: ignore[arg-type]
    await asyncio.gather(*tasks)
    await asyncio.sleep(0)
    assert [t.get_name() for t in tasks] == ['alpha.work', 'alpha.Job']
    assert [c.args[1] for c in on_done.call_args_list] == ['alpha.work', 'alpha.Job']


# ── B96: a route type that cannot carry the auth dependency ──────────────────────────────────────────────────

def _app_with(router: APIRouter, **kw) -> tuple[FastAPI, ModuleManifest]:
    manifest = ModuleManifest(name='files', router=router, **kw)
    return FastAPI(), manifest


@pytest.mark.Trait("Bug", "B96")
def test_a_mount_without_a_public_declaration_is_refused(tmp_path):
    from starlette.staticfiles import StaticFiles
    router = APIRouter()
    router.mount('/files', StaticFiles(directory=tmp_path))
    app, manifest = _app_with(router)
    before = list(app.routes)
    with pytest.raises(ValueError, match='cannot carry the auth dependency'):
        include_module_routers(app, [manifest], auth=_deny)
    assert list(app.routes) == before


@pytest.mark.Trait("Bug", "B96")
def test_a_plain_starlette_route_is_refused():
    async def raw(request):
        return None

    router = APIRouter()
    router.add_route('/raw', raw)
    app, manifest = _app_with(router)
    before = list(app.routes)
    with pytest.raises(ValueError, match='cannot carry the auth dependency'):
        include_module_routers(app, [manifest], auth=_deny)
    assert list(app.routes) == before


@pytest.mark.Trait("Bug", "B96")
def test_a_mount_inside_a_nested_include_is_refused(tmp_path):
    from starlette.staticfiles import StaticFiles
    sub = APIRouter()
    sub.mount('/files', StaticFiles(directory=tmp_path))
    router = APIRouter()
    router.include_router(sub, prefix='/api/x')
    app, manifest = _app_with(router)
    before = list(app.routes)
    with pytest.raises(ValueError, match='cannot carry the auth dependency') as err:
        include_module_routers(app, [manifest], auth=_deny)
    assert '/api/x/files' in str(err.value)
    assert list(app.routes) == before


@pytest.mark.Trait("Bug", "B96")
def test_a_public_mount_is_served(tmp_path):
    from fastapi.testclient import TestClient
    from starlette.staticfiles import StaticFiles
    (tmp_path / 'a.txt').write_text('hello')
    router = APIRouter()
    router.mount('/files', StaticFiles(directory=tmp_path))
    app, manifest = _app_with(router, public_routes=(('MOUNT', '/files'),))
    include_module_routers(app, [manifest], auth=_deny)
    res = TestClient(app).get('/files/a.txt')
    assert res.status_code == 200 and res.text == 'hello'


@pytest.mark.Trait("Bug", "B96")
def test_api_routes_next_to_a_public_mount_keep_auth(tmp_path):
    from fastapi.testclient import TestClient
    from starlette.staticfiles import StaticFiles
    router = APIRouter()
    router.mount('/files', StaticFiles(directory=tmp_path))

    @router.get('/api/x/data')
    async def _data():
        return {}

    app, manifest = _app_with(router, public_routes=(('MOUNT', '/files'),))
    include_module_routers(app, [manifest], auth=_deny)
    assert TestClient(app).get('/api/x/data').status_code == 401


@pytest.mark.Trait("Bug", "B96")
@pytest.mark.parametrize('nested', [False, True], ids=['top-level', 'nested-include'])
def test_a_route_type_without_a_path_is_refused(nested):
    from starlette.routing import Host, Route, Router

    async def handler(request):
        return None

    host = Host('example.test', app=Router([Route('/h', handler)]))
    router = APIRouter()
    if nested:
        sub = APIRouter()
        sub.routes.append(host)
        router.include_router(sub, prefix='/p')
    else:
        router.routes.append(host)
    app, manifest = _app_with(router)
    before = list(app.routes)
    with pytest.raises(ValueError, match='cannot carry the auth dependency'):
        include_module_routers(app, [manifest], auth=_deny)
    assert list(app.routes) == before


# ── B109: a route without explicit methods is not a WebSocket ─────────────────

def _any_method_endpoint():
    from starlette.endpoints import HTTPEndpoint
    from starlette.responses import PlainTextResponse

    class Anything(HTTPEndpoint):
        async def get(self, request):
            return PlainTextResponse('read')

        async def delete(self, request):
            return PlainTextResponse('deleted')

    return Anything


@pytest.mark.Trait("Bug", "B109")
def test_a_route_without_methods_cannot_be_declared_public_as_a_websocket():
    """A class endpoint leaves `Route.methods` None (it answers every method); the loader read that as WEBSOCKET,
    so `('WEBSOCKET', path)` in public_routes served GET and DELETE anonymously."""
    from starlette.routing import Route
    router = APIRouter()
    router.routes.append(Route('/p', _any_method_endpoint()))
    app, manifest = _app_with(router, public_routes=(('WEBSOCKET', '/p'),))
    before = list(app.routes)
    with pytest.raises(ValueError, match='explicit methods'):
        include_module_routers(app, [manifest], auth=_deny)
    assert list(app.routes) == before


@pytest.mark.Trait("Bug", "B109")
def test_a_route_without_methods_is_refused_until_it_names_them():
    from fastapi.testclient import TestClient
    from starlette.routing import Route
    router = APIRouter()
    router.routes.append(Route('/p', _any_method_endpoint()))
    problems = check_modules([ModuleManifest(name='files', router=router)])
    assert len(problems) == 1 and '/p' in problems[0] and 'explicit methods' in problems[0]

    named = APIRouter()
    named.routes.append(Route('/p', _any_method_endpoint(), methods=['GET']))
    # Starlette adds HEAD to a GET route, and a public declaration names every method the route answers
    app, manifest = _app_with(named, public_routes=(('GET', '/p'), ('HEAD', '/p')))
    include_module_routers(app, [manifest], auth=_deny)
    client = TestClient(app)
    assert client.get('/p').status_code == 200
    assert client.delete('/p').status_code == 405


@pytest.mark.Trait("Bug", "B109")
def test_websocket_routes_keep_the_websocket_key():
    from starlette.routing import WebSocketRoute

    from backend.core.modules import _route_keys

    async def ws(websocket):
        return None

    router = APIRouter()

    @router.websocket('/api/x/ws')
    async def _ws(websocket):
        return None

    assert _route_keys(WebSocketRoute('/w', ws)) == {('WEBSOCKET', '/w')}
    assert _route_keys(router.routes[0]) == {('WEBSOCKET', '/api/x/ws')}
    app, manifest = _app_with(router, public_routes=(('WEBSOCKET', '/api/x/ws'),))
    include_module_routers(app, [manifest], auth=_deny)


# ── T605: the loader checks the module routers again at start-up (L1 of the review of T500) ───────────────────

def _nested(path: str = '/api/x') -> tuple[APIRouter, APIRouter]:
    """A module router that includes a sub-router: FastAPI keeps the include lazy, so `sub` can still grow."""
    sub = APIRouter()

    @sub.get('/first')
    async def _first():
        return {}

    router = APIRouter()
    router.include_router(sub, prefix=path)
    return router, sub


def _loaded(router: APIRouter) -> FastAPI:
    app = FastAPI()
    include_module_routers(app, [ModuleManifest(name='alpha', router=router)], auth=_deny)
    return app


@pytest.mark.Trait("Task", "T605")
def test_a_mount_added_to_a_nested_router_after_loading_is_refused_at_start(tmp_path):
    from fastapi.testclient import TestClient
    from starlette.staticfiles import StaticFiles

    from backend.core.modules import recheck_module_routers
    (tmp_path / 'a.txt').write_text('open')
    router, sub = _nested()
    app = _loaded(router)
    sub.mount('/late', StaticFiles(directory=tmp_path))
    # the door this task closes: the late mount is served, and without the auth dependency
    assert TestClient(app).get('/api/x/late/a.txt').status_code == 200
    with pytest.raises(ValueError, match='module routers changed after loading') as err:
        recheck_module_routers(app)
    assert '/api/x/late' in str(err.value)


@pytest.mark.Trait("Task", "T605")
def test_an_api_route_added_to_a_nested_router_after_loading_is_refused_at_start():
    from backend.core.modules import recheck_module_routers
    router, sub = _nested()
    app = _loaded(router)

    @sub.get('/late')
    async def _late():
        return {}

    # it would be guarded, and it is still refused: the served set changed
    with pytest.raises(ValueError, match='module routers changed after loading') as err:
        recheck_module_routers(app)
    assert 'added GET /api/x/late' in str(err.value)


@pytest.mark.Trait("Task", "T605")
def test_a_route_added_to_the_top_router_after_loading_is_refused():
    from fastapi.testclient import TestClient

    from backend.core.modules import recheck_module_routers
    router = _router('/a')
    app = _loaded(router)

    @router.get('/late')
    async def _late():
        return {}

    assert TestClient(app).get('/late').status_code == 404      # the loader copied the top-level routes
    with pytest.raises(ValueError, match='module routers changed after loading') as err:
        recheck_module_routers(app)
    assert 'added GET /late' in str(err.value)


@pytest.mark.Trait("Task", "T605")
def test_a_route_removed_after_loading_is_named_as_missing():
    from backend.core.modules import recheck_module_routers
    router, sub = _nested()
    app = _loaded(router)
    sub.routes.clear()
    with pytest.raises(ValueError, match='module routers changed after loading') as err:
        recheck_module_routers(app)
    assert 'missing GET /api/x/first' in str(err.value)


@pytest.mark.Trait("Task", "T605")
def test_an_unchanged_module_list_passes():
    from backend.core.modules import recheck_module_routers
    router, _sub = _nested()
    app = _loaded(router)
    before = list(app.routes)
    assert recheck_module_routers(app) is None
    assert recheck_module_routers(app) is None                  # it changes nothing, so it can run again
    assert list(app.routes) == before


@pytest.mark.Trait("Task", "T605")
def test_the_real_module_list_passes_the_recheck():
    from backend import main
    from backend.core.modules import recheck_module_routers
    assert recheck_module_routers(main.app) is None


@pytest.mark.Trait("Task", "T605")
def test_the_recheck_is_of_what_was_mounted_not_of_the_current_list(monkeypatch):
    from backend import main
    from backend.core.modules import recheck_module_routers

    async def _task():
        return None

    # as test_b93_lifespan_shutdown.py does before it runs main.lifespan(main.app)
    monkeypatch.setattr(main, 'MODULES', (ModuleManifest(name='probe', router=_router('/probe'), tasks=(_task,)),))
    assert recheck_module_routers(main.app) is None


@pytest.mark.Trait("Task", "T605")
def test_an_app_the_loader_never_saw_is_refused():
    from backend.core.modules import recheck_module_routers
    with pytest.raises(ValueError, match='module routers changed after loading'):
        recheck_module_routers(FastAPI())


@pytest.mark.Trait("Task", "T605")
def test_a_manifest_that_became_invalid_after_loading_is_refused():
    from starlette.routing import Route

    from backend.core.modules import recheck_module_routers
    router, sub = _nested()
    app = _loaded(router)
    # same key as the route that was loaded, so only check_modules can see it: a plain Route carries no auth
    sub.routes.insert(0, Route('/first', _any_method_endpoint(), methods=['GET']))
    with pytest.raises(ValueError, match='module routers changed after loading') as err:
        recheck_module_routers(app)
    assert 'cannot carry the auth dependency' in str(err.value)


@pytest.mark.Trait("Task", "T605")
def test_lifespan_calls_the_recheck_before_any_task_starts():
    tree = ast.parse(MAIN.read_text(encoding='utf-8'))
    lifespan = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == 'lifespan')
    first: dict[str, int] = {}
    for n in ast.walk(lifespan):
        if isinstance(n, ast.Call):
            f = n.func
            name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
            if name:
                first[name] = min(first.get(name, n.lineno), n.lineno)
    recheck = first['recheck_module_routers']
    assert recheck < first['init_pool']
    assert recheck < first['create_task']
    assert recheck < first['start_module_tasks']
    # nothing is caught around the call: it is a statement of the function body itself, with the lifespan's app
    stmt = next(s for s in lifespan.body if isinstance(s, ast.Expr) and isinstance(s.value, ast.Call)
                and getattr(s.value.func, 'id', None) == 'recheck_module_routers')
    assert [getattr(a, 'id', None) for a in stmt.value.args] == ['app']


@pytest.mark.Trait("Task", "T605")
@pytest.mark.asyncio
async def test_lifespan_refuses_to_start_when_a_route_was_added_late(monkeypatch):
    from backend import main
    started: list[str] = []

    async def _init():
        started.append('init_pool')

    monkeypatch.setattr(main, 'init_pool', _init)
    router, sub = _nested()
    app = _loaded(router)

    @sub.get('/late')
    async def _late():
        return {}

    with pytest.raises(ValueError, match='module routers changed after loading'):
        async with main.lifespan(app):
            pass
    assert started == []


@pytest.mark.Trait("Task", "T605")
def test_include_module_routers_records_the_modules_and_their_keys_on_the_app():
    from backend.core.modules import served_keys
    router, _sub = _nested()
    manifests = [ModuleManifest(name='alpha', router=router), ModuleManifest(name='beta'),
                 ModuleManifest(name='gamma', router=_router('/g'))]
    app = FastAPI()
    assert include_module_routers(app, iter(manifests), auth=_deny) is None
    modules, keys = app.state.loaded_modules
    assert modules == tuple(manifests)
    assert keys == served_keys(manifests) == frozenset({('GET', '/api/x/first'), ('GET', '/g')})


@pytest.mark.Trait("Task", "T605")
def test_a_refused_list_leaves_no_record():
    app = FastAPI()
    with pytest.raises(ValueError, match='invalid module list'):
        include_module_routers(app, [ModuleManifest(name='Bad', router=_router('/x'))], auth=_deny)
    assert not hasattr(app.state, 'loaded_modules')
