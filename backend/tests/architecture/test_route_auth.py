"""T402: auth by default. Every route a module serves has the auth dependency unless its manifest declares it public.

The walk reads the real route table of the app (`app.routes`, recursively), not `openapi()`: a route with
`include_in_schema=False` is not in the schema and must not escape the check.
"""
import pytest
from fastapi import APIRouter, Depends, FastAPI, WebSocket

from backend.auth import get_current_user, require_role
from backend.core.modules import ModuleManifest, include_module_routers
from backend.tests.architecture import rules

pytestmark = pytest.mark.Trait("Task", "T402")


def _router() -> APIRouter:
    r = APIRouter(prefix='/api/x')

    @r.get('/open')
    async def _open():
        return {}

    @r.get('/hidden', include_in_schema=False)
    async def _hidden():
        return {}

    @r.put('/admin')
    async def _admin(_=Depends(require_role('admin'))):
        return {}

    @r.websocket('/live')
    async def _live(ws: WebSocket):
        await ws.close()

    return r


def _app_through_the_loader(public=()) -> tuple[FastAPI, list[ModuleManifest]]:
    manifests = [ModuleManifest(name='alpha', router=_router(), public_routes=tuple(public))]
    app = FastAPI()
    include_module_routers(app, manifests, auth=get_current_user)
    return app, manifests


def test_routes_mounted_by_the_loader_all_pass():
    app, manifests = _app_through_the_loader()
    assert rules.check_module_route_auth(app.routes, manifests, get_current_user) == []


def test_a_declared_public_route_passes_and_an_undeclared_one_does_not():
    app, manifests = _app_through_the_loader(public=[('GET', '/api/x/open')])
    assert rules.check_module_route_auth(app.routes, manifests, get_current_user) == []
    # the same route table, but the manifest does not declare the route any more: the check names it
    undeclared = [ModuleManifest(name='alpha', router=manifests[0].router)]
    problems = rules.check_module_route_auth(app.routes, undeclared, get_current_user)
    assert len(problems) == 1 and '/api/x/open' in problems[0] and 'alpha' in problems[0]


def test_a_route_mounted_without_the_loader_is_found_even_when_hidden_from_the_schema():
    manifests = [ModuleManifest(name='alpha', router=_router())]
    app = FastAPI()
    app.include_router(manifests[0].router)          # bypasses the loader: no auth dependency
    problems = rules.check_module_route_auth(app.routes, manifests, get_current_user)
    text = '\n'.join(problems)
    assert '/api/x/open' in text and '/api/x/hidden' in text and '/api/x/live' in text
    assert '/api/x/hidden' not in app.openapi()['paths']          # proves the walk is not the schema
    assert '/api/x/admin' not in text                            # require_role depends on get_current_user


def test_a_route_that_is_not_mounted_at_all_is_reported():
    manifests = [ModuleManifest(name='alpha', router=_router())]
    problems = rules.check_module_route_auth(FastAPI().routes, manifests, get_current_user)
    assert any('not mounted' in p for p in problems)


def test_every_route_of_every_real_module_has_auth_or_is_declared_public():
    from backend.main import app
    from backend.modules import MODULES
    assert rules.check_module_route_auth(app.routes, list(MODULES), get_current_user) == []


def test_the_settings_module_declares_no_public_route():
    from backend.modules import MODULES
    settings = next(m for m in MODULES if m.name == 'settings')
    assert settings.public_routes == ()


# ── B96: a Mount or a plain route is a route too ──────────────────────────────────────────────────────────────

@pytest.mark.Trait("Bug", "B96")
def test_a_mount_added_around_the_loader_is_reported(tmp_path):
    from starlette.staticfiles import StaticFiles
    router = APIRouter()
    router.mount('/files', StaticFiles(directory=tmp_path))
    manifests = [ModuleManifest(name='alpha', router=router)]
    app = FastAPI()
    app.include_router(router)
    app.mount('/files', StaticFiles(directory=tmp_path))
    problems = rules.check_module_route_auth(app.routes, manifests, get_current_user)
    text = '\n'.join(problems)
    assert '/files' in text and 'Mount' in text


@pytest.mark.Trait("Bug", "B96")
def test_effective_routes_lists_a_static_mount(tmp_path):
    from starlette.staticfiles import StaticFiles
    direct = APIRouter()
    direct.mount('/files', StaticFiles(directory=tmp_path))
    sub = APIRouter()
    sub.mount('/files', StaticFiles(directory=tmp_path))
    nested = APIRouter()
    nested.include_router(sub, prefix='/api/x')
    for router, path in ((direct, '/files'), (nested, '/api/x/files')):
        found = rules.effective_routes(router.routes)
        assert any(r.path == path and r.methods == frozenset({'MOUNT'}) for r in found), (path, found)
