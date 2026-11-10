"""Module manifest contract: what a module declares is checked here, before step 1 creates the first module."""
import json
from pathlib import Path

import pytest

from backend.core.modules import ModuleManifest, validate_manifest
from backend.tests.architecture import rules

REPO = Path(__file__).resolve().parents[3]
BACKEND = REPO / 'backend'
TOML = Path(__file__).with_name('importlinter.toml')
ALLOWLIST = Path(__file__).with_name('allowlist.json')


def _backend(tmp_path, *folders: str) -> Path:
    for f in folders:
        (tmp_path / 'modules' / f).mkdir(parents=True)
    return tmp_path


@pytest.mark.Trait('Task', 'T305')
def test_manifest_defaults_are_empty_and_valid():
    m = ModuleManifest(name='people')
    assert (m.owns_tables, m.reads_tables, m.depends_on, m.router, m.tasks, m.live_messages, m.subscriptions) == \
        ((), (), (), None, (), (), ())
    assert validate_manifest(m) == []


@pytest.mark.Trait('Task', 'T305')
@pytest.mark.parametrize('name', ['People', '1people', '', 'my-module', 'a b', 'x\n'])
def test_validate_manifest_refuses_bad_names(name):
    assert any('name' in p for p in validate_manifest(ModuleManifest(name=name)))


@pytest.mark.Trait('Task', 'T305')
def test_validate_manifest_rules(tmp_path):
    backend = _backend(tmp_path, 'people', 'teams', 'devices')
    ok = [
        ModuleManifest(name='people', owns_tables=('users',), live_messages=('person_changed',)),
        ModuleManifest(name='teams', owns_tables=('groups', 'user_groups'), depends_on=('people',)),
        ModuleManifest(name='devices', owns_tables=('devices',), depends_on=('people',)),
    ]
    assert rules.check_manifests(ok, backend) == []

    def problems(*ms):
        return rules.check_manifests(list(ms), backend)

    # intrinsic rules (core.validate_manifest)
    assert validate_manifest(ModuleManifest(name='teams', depends_on=('teams',)))
    assert validate_manifest(ModuleManifest(name='teams', owns_tables=('groups', 'groups')))
    assert validate_manifest(ModuleManifest(name='teams', owns_tables=('groups',), reads_tables=('groups',)))
    assert validate_manifest(ModuleManifest(name='teams', live_messages=('a', 'a')))
    assert validate_manifest(ModuleManifest(name='teams', live_messages=('',)))
    # the name must match a folder
    assert any('folder' in p for p in problems(ModuleManifest(name='ghost')))
    # an owned table must belong to this module
    assert any('users' in p for p in problems(ModuleManifest(name='teams', owns_tables=('users',))))
    assert any('nope' in p for p in problems(ModuleManifest(name='teams', owns_tables=('nope',))))
    # dependencies must exist and be allowed edges
    assert any('ghost' in p for p in problems(ModuleManifest(name='teams', depends_on=('ghost',))))
    assert any('not allowed' in p for p in problems(
        ModuleManifest(name='people', depends_on=('teams',)), ModuleManifest(name='teams')))
    # live message names are unique across modules
    dup = problems(ModuleManifest(name='people', live_messages=('ping',)),
                   ModuleManifest(name='teams', live_messages=('ping',)))
    assert any('ping' in p and 'people' in p and 'teams' in p for p in dup)
    # two manifests with one name
    assert any('twice' in p for p in problems(ModuleManifest(name='people'), ModuleManifest(name='people')))


@pytest.mark.Trait('Task', 'T305')
def test_allowed_edges_are_themselves_acyclic_and_name_known_modules():
    assert rules.find_cycle(rules.ALLOWED_EDGES) is None
    known = set(rules.TABLE_OWNER.values()) | {'gateway', 'simulation', 'identity', 'reporting', 'maps', 'weather'}
    assert {n for e in rules.ALLOWED_EDGES for n in e} <= known
    assert ('simulation', 'people') in rules.ALLOWED_EDGES and ('fire', 'settings') in rules.ALLOWED_EDGES


@pytest.mark.Trait('Task', 'T305')
def test_graph_has_no_cycles(tmp_path):
    backend = _backend(tmp_path, 'people', 'teams', 'devices')
    cyc = [ModuleManifest(name='people', depends_on=('teams',)), ModuleManifest(name='teams', depends_on=('people',))]
    assert any('cycle' in p for p in rules.check_manifests(cyc, backend))
    assert rules.find_cycle({('a', 'b'), ('b', 'c'), ('c', 'a')}) is not None
    assert rules.find_cycle({('a', 'b'), ('b', 'c'), ('a', 'c')}) is None
    assert rules.find_cycle({('a', 'a')}) is not None


def _toml_with(*names: str) -> str:
    return ''.join(f'[[tool.importlinter.contracts]]\nname = "module boundary: {n}"\n' for n in names)


@pytest.mark.Trait('Task', 'T305')
def test_real_module_list_is_complete():
    from backend.modules import MODULES
    toml_text = TOML.read_text(encoding='utf-8')
    assert rules.check_module_list(BACKEND, MODULES, toml_text) == []
    assert rules.check_manifests(list(MODULES), BACKEND) == []
    assert rules.check_boundary_contracts(toml_text, [m.name for m in MODULES], BACKEND) == []
    assert rules.check_manifest_wiring(list(MODULES), BACKEND) == []


@pytest.mark.Trait('Task', 'T305')
def test_module_list_check_bites_on_a_tmp_tree(tmp_path):
    backend = _backend(tmp_path, 'people', 'teams', 'no_manifest', '__pycache__')
    (backend / 'modules' / 'people' / 'module.py').write_text('', encoding='utf-8')
    (backend / 'modules' / 'teams' / 'module.py').write_text('', encoding='utf-8')
    people, teams = ModuleManifest(name='people'), ModuleManifest(name='teams')   # no_manifest has no module.py
    full_toml = _toml_with('people', 'teams')
    assert rules.check_module_list(backend, (people, teams), full_toml) == []
    assert any('teams' in p and 'MODULES' in p for p in rules.check_module_list(backend, (people,), full_toml))
    assert any('module boundary: teams' in p
               for p in rules.check_module_list(backend, (people, teams), _toml_with('people')))
    assert any('ghost' in p for p in rules.check_module_list(backend, (people, teams, ModuleManifest(name='ghost')), full_toml))


@pytest.mark.Trait('Task', 'T305')
def test_end_state():
    data = json.loads(ALLOWLIST.read_text(encoding='utf-8'))
    if data['completed_step'] < 5:
        pytest.skip(f"completed_step is {data['completed_step']}: the end state is checked at step 5")
    assert rules.end_state_problems(data, TOML.read_text(encoding='utf-8'), BACKEND) == []


@pytest.mark.Trait('Task', 'T305')
def test_end_state_rules_bite_at_step_5(tmp_path):
    clean_toml = '[[tool.importlinter.contracts]]\nname = "c"\nignore_imports = []\n'
    dirty_toml = '[[tool.importlinter.contracts]]\nname = "c"\nignore_imports = ["a -> b"]\n'
    done = {'completed_step': 5, 'sql_writes': []}
    row = {'file': 'main.py', 'table': 'users', 'verb': 'INSERT', 'until': 5}
    assert rules.end_state_problems(done, clean_toml, tmp_path) == []
    assert rules.end_state_problems({'completed_step': 4, 'sql_writes': [row]}, dirty_toml, tmp_path) == []
    assert any('sql_writes' in p for p in rules.end_state_problems({**done, 'sql_writes': [row]}, clean_toml, tmp_path))
    assert any('ignore_imports' in p for p in rules.end_state_problems(done, dirty_toml, tmp_path))
    for shim in ('config', 'database', 'json_columns', 'ws'):
        (tmp_path / f'{shim}.py').write_text('', encoding='utf-8')
    probs = rules.end_state_problems(done, clean_toml, tmp_path)
    assert all(any(f'{s}.py' in p for p in probs) for s in ('config', 'database', 'json_columns', 'ws'))


def _boundary_toml(name: str, forbidden: list[str], sources: list[str], kind: str = 'forbidden') -> str:
    def lst(items):
        return '[' + ', '.join(f'"{i}"' for i in items) + ']'
    return (f'[[tool.importlinter.contracts]]\nname = "module boundary: {name}"\ntype = "{kind}"\n'
            f'source_modules = {lst(sources)}\nforbidden_modules = {lst(forbidden)}\n')


def _two_modules(tmp_path) -> Path:
    for name in ('a', 'b'):
        mod = tmp_path / 'modules' / name
        (mod / 'domain').mkdir(parents=True)
        (mod / 'domain' / '__init__.py').write_text('', encoding='utf-8')
        (mod / '__pycache__').mkdir()
        for f in ('api.py', 'http.py', '__init__.py'):
            (mod / f).write_text('', encoding='utf-8')
    return tmp_path


def _complete_toml(forbidden_of_a=None, sources_of_a=None) -> str:
    private = ['backend.modules.{n}.http', 'backend.modules.{n}.domain']
    legacy = list(rules.LEGACY_SOURCES)
    a_forbidden = forbidden_of_a if forbidden_of_a is not None else [f.format(n='a') for f in private]
    a_sources = sources_of_a if sources_of_a is not None else legacy + ['backend.modules.b']
    return (_boundary_toml('a', a_forbidden, a_sources)
            + _boundary_toml('b', [f.format(n='b') for f in private], legacy + ['backend.modules.a']))


@pytest.mark.Trait('Task', 'T401')
def test_boundary_contract_rules_bite_on_a_tmp_tree(tmp_path):
    backend = _two_modules(tmp_path)
    legacy = list(rules.LEGACY_SOURCES)
    assert rules.check_boundary_contracts(_complete_toml(), ['a', 'b'], backend) == []
    # the other module missing from the sources
    probs = rules.check_boundary_contracts(_complete_toml(sources_of_a=legacy), ['a', 'b'], backend)
    assert len(probs) == 1 and 'module boundary: a' in probs[0]
    # a legacy source missing
    probs = rules.check_boundary_contracts(
        _complete_toml(sources_of_a=legacy[1:] + ['backend.modules.b']), ['a', 'b'], backend)
    assert len(probs) == 1 and 'module boundary: a' in probs[0]
    # a private child missing from the forbidden list
    probs = rules.check_boundary_contracts(
        _complete_toml(forbidden_of_a=['backend.modules.a.domain']), ['a', 'b'], backend)
    assert len(probs) == 1 and 'module boundary: a' in probs[0]
    # the public api forbidden
    probs = rules.check_boundary_contracts(
        _complete_toml(forbidden_of_a=['backend.modules.a.http', 'backend.modules.a.domain', 'backend.modules.a.api']),
        ['a', 'b'], backend)
    assert len(probs) == 1 and 'module boundary: a' in probs[0]
    # no contract at all for b
    only_a = _boundary_toml('a', ['backend.modules.a.http', 'backend.modules.a.domain'], legacy + ['backend.modules.b'])
    probs = rules.check_boundary_contracts(only_a, ['a', 'b'], backend)
    assert len(probs) == 1 and 'module boundary: b' in probs[0]
    # a contract of the wrong type
    wrong = _boundary_toml('a', ['backend.modules.a.http', 'backend.modules.a.domain'],
                           legacy + ['backend.modules.b'], kind='layers')
    probs = rules.check_boundary_contracts(wrong, ['a'], backend)
    assert len(probs) == 1 and 'module boundary: a' in probs[0]


async def _task_outside_the_tasks_module():
    return None


def _sync_task():
    return None


@pytest.mark.Trait('Task', 'T401')
def test_manifest_wiring_rules_bite(tmp_path):
    from fastapi import APIRouter
    backend = _two_modules(tmp_path)   # a has an http.py on disk; b has one too, but neither is importable
    (backend / 'modules' / 'b' / 'http.py').unlink()
    assert rules.check_manifest_wiring([ModuleManifest(name='b')], backend) == []
    # router declared although there is no http.py
    probs = rules.check_manifest_wiring([ModuleManifest(name='b', router=APIRouter())], backend)
    assert len(probs) == 1 and 'b' in probs[0]
    # http.py exists but the router is not the router of backend.modules.a.http
    probs = rules.check_manifest_wiring([ModuleManifest(name='a', router=APIRouter())], backend)
    assert len(probs) == 1 and 'a' in probs[0]
    # unknown live message
    probs = rules.check_manifest_wiring([ModuleManifest(name='b', live_messages=('nope',))], backend)
    assert len(probs) == 1 and 'nope' in probs[0]
    # a task that is not a coroutine function, and one that lives outside backend.modules.b.tasks
    probs = rules.check_manifest_wiring([ModuleManifest(name='b', tasks=(_sync_task,))], backend)
    assert len(probs) == 1 and '_sync_task' in probs[0]
    probs = rules.check_manifest_wiring([ModuleManifest(name='b', tasks=(_task_outside_the_tasks_module,))], backend)
    assert len(probs) == 1 and '_task_outside_the_tasks_module' in probs[0]


@pytest.mark.Trait('Task', 'T401')
def test_shims_and_fire_private_contracts_cover_modules():
    import tomllib
    contracts = {c['id']: c for c in tomllib.loads(TOML.read_text(encoding='utf-8'))['tool']['importlinter']['contracts']}
    for cid in ('shims', 'fire-private'):
        assert 'backend.modules' in contracts[cid]['source_modules'], cid


@pytest.mark.Trait("Task", "T402")
def test_manifest_wiring_accepts_the_real_settings_module():
    import dataclasses

    from fastapi import APIRouter

    from backend.modules.settings.module import manifest
    assert rules.check_manifest_wiring([manifest], BACKEND) == []
    # and it fails on the comparison itself (not on an import error) when the router is another one
    probs = rules.check_manifest_wiring([dataclasses.replace(manifest, router=APIRouter())], BACKEND)
    assert len(probs) == 1 and 'is not the `router` of backend.modules.settings.http' in probs[0]
