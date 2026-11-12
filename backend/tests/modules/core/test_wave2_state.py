"""T590: what wave 2 reached on `develop`, pinned as lower bounds and membership.

Later waves only extend this (step 3 adds `gateway`, step 4 removes `module_edges` rows), so nothing here asserts an
exact list, an order or a count. The detachable tasks are not asserted: T542 and T547 have their own tests
(`gateway/test_reader_delegates.py`, `tracking/test_thin_payload.py`); T548 and T549 are not merged.
"""

import importlib
import json
from pathlib import Path

import pytest
from starlette.routing import Mount

from backend.tests.architecture import rules
from backend.tests.architecture.approved_additions import APPROVED

REPO = Path(__file__).resolve().parents[4]
ALLOWLIST_REL = 'backend/tests/architecture/allowlist.json'
ALLOWLIST = REPO / ALLOWLIST_REL
MAIN = REPO / 'backend' / 'main.py'

# The old import paths of the fire package and of its router: aliases of the module until step 5.
OLD_FIRE_PATHS = (
    'backend.fire.h3index',
    'backend.fire.models',
    'backend.fire.parse',
    'backend.fire.poller',
    'backend.fire.proximity',
    'backend.fire.repository',
    'backend.fire.service',
    'backend.fire.sources',
    'backend.routers.fire',
)


def _allowlist() -> dict:
    return json.loads(ALLOWLIST.read_text(encoding='utf-8'))


@pytest.mark.Trait("Task", "T590")
def test_fire_tracking_sos_and_weather_are_modules():
    import backend.modules
    names = [m.name for m in backend.modules.MODULES]
    for name in ('fire', 'tracking', 'sos', 'weather'):
        assert name in names, name
    assert _allowlist()['completed_step'] >= 2


@pytest.mark.Trait("Task", "T590")
def test_main_names_none_of_them():
    source = MAIN.read_text(encoding='utf-8')
    for gone in ('fire_poller', 'fire_alarm', 'fire.router', 'locations.router', 'weather.router'):
        assert gone not in source, f'backend/main.py still names {gone}'


@pytest.mark.Trait("Task", "T590")
@pytest.mark.parametrize('dotted', OLD_FIRE_PATHS)
def test_the_old_fire_paths_are_aliases(dotted):
    mod = importlib.import_module(dotted)
    assert mod.__name__.startswith('backend.modules.fire'), f'{dotted} is {mod.__name__}, not an alias of the module'


@pytest.mark.Trait("Task", "T590")
def test_no_writer_outside_the_owning_module():
    rows = _allowlist()['sql_writes']
    moved_files = {'routers/test.py', 'routers/users.py', 'routers/devices.py'}
    left = [r for r in rows if r['file'] in moved_files]
    left += [r for r in rows if r['file'] == 'simulation.py' and r['table'] in ('location_events', 'sos_alerts')]
    assert left == [], f'these writers go through the owning module api.py: {left}'


@pytest.mark.Trait("Task", "T590")
def test_reverse_edges_are_named():
    approved = APPROVED.get(ALLOWLIST_REL, {})
    for row in _allowlist()['module_edges']:
        assert row['until'] in (3, 4), f'a reverse edge ends with the gateway step or the events step: {row}'
        key = 'module_edges: ' + json.dumps(row, sort_keys=True)
        assert len(approved.get(key, '').strip()) >= 20, f'no approval with a reason for {row}'


@pytest.mark.Trait("Task", "T590")
def test_no_module_router_holds_a_mount():
    import backend.modules
    seen = 0
    for m in backend.modules.MODULES:
        if m.router is None:
            continue
        seen += 1
        public = set(m.public_routes)
        top_level = {id(r) for r in m.router.routes if isinstance(r, Mount)}
        for route in m.router.routes:
            if isinstance(route, Mount):
                assert ('MOUNT', route.path) in public, f'{m.name}: mount {route.path} is not in public_routes'
        # nested includes: a mount inside one cannot be declared public, so there may be none at all
        mounts = [r for r in rules.effective_routes(m.router.routes) if r.kind == 'Mount']
        assert len(mounts) <= len(top_level), f'{m.name}: a mount sits inside a nested include: {mounts}'
    assert seen >= 4       # fire, tracking, sos and weather each serve a router
