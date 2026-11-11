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

# Production files that belong to no module on purpose: the assembly. Anything else without an owner is a mistake.
OWNERLESS_IMPORTERS = frozenset({'backend.main'})


def _ownerless_importers(imports) -> set[str]:
    """Production importers of a module (`backend.modules.<x>`, kernel children aside) that have no owner."""
    prefix = 'backend.modules.'
    found = set()
    for importer, imported in imports:
        if not imported.startswith(prefix) or imported[len(prefix):].split('.')[0] in rules.KERNEL_CHILDREN:
            continue
        if importer.startswith('backend.tests.') or importer == 'backend.tests':
            continue
        if not rules._owners_of_dotted(importer):
            found.add(importer)
    return found


@pytest.mark.Trait("Task", "T590")
def test_an_importer_without_an_owner_is_only_the_assembly():
    """The direction rule lets an ownerless importer through; that is meant for main.py and for nothing else."""
    assert _ownerless_importers([
        ('backend.brand_new', 'backend.modules.fire.api'),          # unmapped file: no owner
        ('backend.main', 'backend.modules.fire.api'),
        ('backend.brand_new', 'backend.modules.registry'),          # kernel child, not a module
        ('backend.tests.test_x', 'backend.modules.fire.api'),       # tests are outside the rule
        ('backend.routers.users', 'backend.modules.people.api'),    # has an owner
    ]) == {'backend.brand_new', 'backend.main'}
    extra = sorted(_ownerless_importers(_real_imports()) - OWNERLESS_IMPORTERS)
    assert not extra, f'give these files an owner in module_map.MODULE_OF_FILE (ownerless code passes the edge rule): {extra}'


@pytest.mark.Trait("Task", "T590")
def test_kernel_children_are_core_files_not_packages():
    """`KERNEL_CHILDREN` switches the edge rule off for a name: only a single kernel file owned by `core` may be there."""
    from backend.tests.architecture import module_map
    for child in rules.KERNEL_CHILDREN:
        assert (REPO / 'backend' / 'modules' / f'{child}.py').is_file(), f'{child} must be the file modules/{child}.py'
        assert not (REPO / 'backend' / 'modules' / child).exists(), f'{child} is a package: it is a module, not a kernel file'
        assert module_map.owners_of(f'modules/{child}.py') == ('core',), child
