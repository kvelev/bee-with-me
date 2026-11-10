"""T400: the kernel mounts routers and starts tasks from the module list; main.py reads it."""
import ast
import asyncio
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi import APIRouter, FastAPI

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


def _paths(app: FastAPI) -> list[str]:
    # newer FastAPI keeps an included router as one lazy route object without a path: read the schema instead
    return list(app.openapi()['paths'])


@pytest.mark.Trait("Task", "T400")
def test_include_module_routers_mounts_in_list_order():
    app = FastAPI()
    include_module_routers(app, [ModuleManifest(name='alpha', router=_router('/a')),
                                 ModuleManifest(name='beta', router=_router('/b'))])
    assert _paths(app)[-2:] == ['/a', '/b']


@pytest.mark.Trait("Task", "T400")
def test_a_manifest_without_router_is_skipped():
    app = FastAPI()
    before = list(app.routes)
    include_module_routers(app, [ModuleManifest(name='gamma')])
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
        include_module_routers(app, modules)
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
