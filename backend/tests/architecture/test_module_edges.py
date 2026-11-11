"""Calls between modules follow the allowed edges; today's exceptions are allowlisted and may only shrink."""
import json
from pathlib import Path

import pytest

from backend.tests.architecture import rules
from backend.tests.architecture.tooling import require_import_linter

grimp = require_import_linter('grimp')   # installed together with import-linter (requirements-dev.txt)

REPO = Path(__file__).resolve().parents[3]
ALLOWLIST = Path(__file__).with_name('allowlist.json')


def _data() -> dict:
    return json.loads(ALLOWLIST.read_text(encoding='utf-8'))


def _graph():
    import sys
    sys.path.insert(0, str(REPO))
    try:
        return grimp.build_graph('backend', include_external_packages=False)
    finally:
        sys.path.remove(str(REPO))


def _real_imports() -> set[tuple[str, str]]:
    graph = _graph()
    return {(importer, imported)
            for importer in graph.modules
            for imported in graph.find_modules_directly_imported_by(importer)}


@pytest.mark.Trait('Task', 'T501')
def test_direction_rule_bites():
    bad = rules.module_edge_violations([
        ('backend.routers.users', 'backend.modules.fire.api'),                       # people -> fire: not allowed
        ('backend.fire.repository', 'backend.modules.fire.infrastructure.repository'),   # same owner
        ('backend.hardware_reader.reader', 'backend.modules.tracking.api'),          # gateway -> tracking: allowed
        ('backend.main', 'backend.modules.fire.api'),                                # assembly
        ('backend.modules.settings.http', 'backend.modules.fire.api'),               # settings -> fire: not allowed
        ('backend.routers.locations', 'backend.modules.sos.http'),                   # owners tracking and sos
        ('backend.modules.registry', 'backend.modules.fire.module'),                 # core
        ('backend.routers.users', 'backend.modules.registry'),                       # registry is core, not a module
        ('backend.routers.users', 'backend.fire.api'),                               # not under backend.modules
    ])
    assert bad == {
        ('backend.routers.users', 'backend.modules.fire.api'),
        ('backend.modules.settings.http', 'backend.modules.fire.api'),
    }


@pytest.mark.Trait('Task', 'T501')
def test_the_graph_sees_function_level_and_lazy_imports():
    graph = _graph()
    assert 'backend.hardware_reader.hid_reader' in graph.find_modules_directly_imported_by('backend.main')
    assert 'backend.modules.registry' in graph.find_modules_directly_imported_by('backend.modules')


@pytest.mark.Trait('Task', 'T501')
def test_real_module_edges_match_the_allowlist_exactly():
    found = rules.module_edge_violations(_real_imports())
    allowed = {(r['from'], r['to']) for r in _data()['module_edges']}
    new = sorted(found - allowed)
    stale = sorted(allowed - found)
    assert not new, f'add the edge to ALLOWED_EDGES or carry it in module_edges with an approval: {new}'
    assert not stale, f'delete this row from module_edges: {stale}'


@pytest.mark.Trait('Task', 'T501')
def test_module_edge_rows_are_not_overdue():
    data = _data()
    for row in data['module_edges']:
        assert set(row) == {'from', 'to', 'until'}, row
        assert 1 <= row['until'] <= 5, row
        assert row['until'] > data['completed_step'], f'overdue, remove the edge: {row}'
