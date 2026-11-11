"""T460: what wave 1 reached, pinned as lower bounds and membership.

Later steps only extend this (step 2 adds `fire` to MODULES and removes allowlist lines), so nothing here asserts an
exact list or a count. The size of the import allowlist is deliberately not asserted: the ratchet guards its growth.
"""

import ast
import importlib
import json
import sys
import types
from pathlib import Path

import pytest
from fastapi import APIRouter

REPO = Path(__file__).resolve().parents[4]
ALLOWLIST = REPO / 'backend' / 'tests' / 'architecture' / 'allowlist.json'
MAIN = REPO / 'backend' / 'main.py'


@pytest.mark.Trait("Task", "T460")
def test_settings_is_a_module_and_step_1_is_recorded():
    import backend.modules
    assert 'settings' in [m.name for m in backend.modules.MODULES]
    assert json.loads(ALLOWLIST.read_text(encoding='utf-8'))['completed_step'] >= 1


def _absolute(node: ast.ImportFrom) -> str:
    """Dotted module of a `from ... import` in backend/main.py (`.routers` -> `backend.routers`)."""
    tail = node.module or ''
    if node.level == 0:
        return tail
    return 'backend' + ('.' + tail if tail else '')


def _is_module_code(dotted: str) -> bool:
    return dotted == 'backend.modules' or dotted.startswith('backend.modules.')


def _module_problem(dotted: str) -> str | None:
    """Why `dotted` (a module under backend.routers) is not a legacy router, or None when it is one."""
    try:
        mod = importlib.import_module(dotted)
    except ModuleNotFoundError:
        return None  # a name that is not a module (an attribute of the package): nothing to mount
    if _is_module_code(mod.__name__):
        return 'an alias of ' + mod.__name__
    router = getattr(mod, 'router', None)
    if router is None:
        return None
    for route in getattr(router, 'routes', []):
        home = getattr(getattr(route, 'endpoint', None), '__module__', '') or ''
        if _is_module_code(home):
            return 'a shim: its router serves ' + home
    for name, other in list(sys.modules.items()):
        if _is_module_code(name) and getattr(other, 'router', None) is router:
            return 'a shim: its router is the one of ' + name
    return None


def router_problems(source: str) -> list[str]:
    """Problems of main.py's way to mount routers: one per router module that is really module code.

    Names nothing: it follows every `include_router(...)` argument and every name imported from `.routers`, and asks
    the imported module what it is, so an alias, a re-export or a router renamed by hand cannot get past it.
    """
    tree = ast.parse(source)
    imported: dict[str, tuple[str, int]] = {}      # local name -> (dotted target, line)
    candidates: dict[str, int] = {}                # backend.routers.<x> -> first line that names it
    problems: list[str] = []

    def candidate(dotted: str, line: int) -> None:
        candidates[dotted] = min(line, candidates.get(dotted, line))

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            base = _absolute(node)
            for alias in node.names:
                imported[alias.asname or alias.name] = (f'{base}.{alias.name}', node.lineno)
                if base == 'backend.routers':
                    candidate(f'{base}.{alias.name}', node.lineno)
                elif base.startswith('backend.routers.') and alias.name != '*':
                    candidate(base, node.lineno)
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'include_router'):
            continue
        for arg in node.args:
            root = arg
            while isinstance(root, ast.Attribute):
                root = root.value
            if not isinstance(root, ast.Name) or root.id not in imported:
                continue
            target = imported[root.id][0]
            if _is_module_code(target):
                problems.append(f'main.py line {node.lineno}: include_router mounts {target}, a module mounts its own router')
    for dotted, line in sorted(candidates.items(), key=lambda kv: kv[1]):
        why = _module_problem(dotted)
        if why:
            problems.append(f'main.py line {line}: {dotted} is {why}; a module mounts its own router')
    return problems


@pytest.mark.Trait("Task", "T460")
@pytest.mark.Trait("Task", "T582")
def test_main_names_no_module_router():
    assert router_problems(MAIN.read_text(encoding='utf-8')) == []


@pytest.mark.Trait("Task", "T582")
def test_the_router_check_bites_on_an_alias_and_on_a_shim(monkeypatch):
    # an alias: routers.settings IS backend.modules.settings.http (sys.modules swap)
    alias = router_problems('from .routers import settings as s\napp.include_router(s.router)')
    assert len(alias) == 1 and 'line 1' in alias[0] and 'backend.routers.settings' in alias[0]
    assert router_problems('from .routers import auth\napp.include_router(auth.router)') == []

    # a shim: a routers module of its own name whose router serves module code
    def handler():  # pragma: no cover
        return None
    handler.__module__ = 'backend.modules.fake.http'
    shim = types.ModuleType('backend.routers._t582_shim')
    shim.router = APIRouter()
    shim.router.add_api_route('/x', handler)
    monkeypatch.setitem(sys.modules, 'backend.routers._t582_shim', shim)
    problems = router_problems('from .routers import _t582_shim as sh\n\napp.include_router(sh.router)')
    assert len(problems) == 1 and 'a shim' in problems[0]

    # a re-export of an empty router object (identity), mounted through a renamed import
    shared = APIRouter()
    owner = types.ModuleType('backend.modules._t582_owner')
    owner.router = shared
    again = types.ModuleType('backend.routers._t582_again')
    again.router = shared
    monkeypatch.setitem(sys.modules, 'backend.modules._t582_owner', owner)
    monkeypatch.setitem(sys.modules, 'backend.routers._t582_again', again)
    problems = router_problems('from .routers._t582_again import router as r\napp.include_router(r)')
    assert len(problems) == 1 and 'line 1' in problems[0]

    # mounting a router straight from module code
    assert len(router_problems('from .modules.settings.http import router\napp.include_router(router)')) == 1
