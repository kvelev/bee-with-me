"""Rules of the module architecture that are data: table owners, allowed module edges and the checks over them."""
from __future__ import annotations

import tomllib
from collections.abc import Iterable
from pathlib import Path

from backend.core.modules import ModuleManifest, validate_manifest
from backend.tests.architecture import module_map

TABLE_OWNER: dict[str, str] = {
    'users': 'people',
    'groups': 'teams', 'user_groups': 'teams',
    'devices': 'devices',
    'location_events': 'tracking', 'repeater_events': 'tracking',
    'sos_alerts': 'sos',
    'fire_hotspots': 'fire', 'fire_burnt_areas': 'fire', 'fire_alerts': 'fire', 'fire_suppression_zones': 'fire',
    'settings': 'settings',
    'schema_migrations': 'core',
}

# modular-monolith.md 4.2, plus `simulation -> people, devices, teams` (spec, step 4). (caller, callee)
ALLOWED_EDGES: frozenset[tuple[str, str]] = frozenset({
    ('gateway', 'tracking'), ('gateway', 'sos'), ('gateway', 'devices'),
    ('simulation', 'gateway'), ('simulation', 'people'), ('simulation', 'devices'), ('simulation', 'teams'),
    ('tracking', 'devices'),
    ('sos', 'devices'),
    ('fire', 'tracking'), ('fire', 'settings'), ('fire', 'devices'), ('fire', 'people'),
    ('reporting', 'tracking'), ('reporting', 'sos'), ('reporting', 'people'), ('reporting', 'teams'),
    ('reporting', 'devices'),
    ('identity', 'people'),
    ('teams', 'people'),
    ('devices', 'people'),
})

SHIM_FILES = ('config', 'database', 'json_columns', 'ws')


# ── SQL ownership ─────────────────────────────────────────────────────────────

def sql_violations(writes: Iterable[tuple[str, str, str]]) -> set[tuple[str, str, str]]:
    """Writes whose table is owned by a module that does not own the writing file.

    Tables without an owner are not reported here (`test_every_scanned_table_has_an_owner` catches them).
    """
    bad: set[tuple[str, str, str]] = set()
    for file, table, verb in writes:
        owner = TABLE_OWNER.get(table)
        if owner is not None and owner not in module_map.owners_of(file):
            bad.add((file, table, verb))
    return bad


def until_step(file: str, table: str) -> int:
    """Step at which a violation must be gone: the table owner's step; main.py and db/** follow STEP_OVERRIDE."""
    dotted = 'backend.' + file.removesuffix('.py').replace('/', '.')
    for prefix, step in module_map.STEP_OVERRIDE.items():
        if dotted == prefix or dotted.startswith(prefix + '.'):
            return step
    return module_map.STEP_OF_MODULE[TABLE_OWNER[table]]


# ── module graph ──────────────────────────────────────────────────────────────

def find_cycle(edges: Iterable[tuple[str, str]]) -> list[str] | None:
    """A cycle `[a, b, ..., a]` in the directed graph, or None."""
    graph: dict[str, list[str]] = {}
    for a, b in edges:
        graph.setdefault(a, []).append(b)
        graph.setdefault(b, [])
    state: dict[str, int] = {}   # 1 = on the current path, 2 = done

    def visit(node: str, path: list[str]) -> list[str] | None:
        state[node] = 1
        path.append(node)
        for nxt in sorted(graph[node]):
            if state.get(nxt) == 1:
                return path[path.index(nxt):] + [nxt]
            if nxt not in state:
                found = visit(nxt, path)
                if found:
                    return found
        path.pop()
        state[node] = 2
        return None

    for start in sorted(graph):
        if start not in state:
            found = visit(start, [])
            if found:
                return found
    return None


def check_manifests(manifests: Iterable[ModuleManifest], backend: Path) -> list[str]:
    """Cross-module checks over the declared manifests; an empty list means they are consistent."""
    manifests = list(manifests)
    problems: list[str] = []
    names = [m.name for m in manifests]
    for name in sorted({n for n in names if names.count(n) > 1}):
        problems.append(f'module {name!r} is listed twice in MODULES')
    known = set(names)
    messages: dict[str, list[str]] = {}
    edges: set[tuple[str, str]] = set()
    for m in manifests:
        problems += validate_manifest(m)
        if not (backend / 'modules' / m.name).is_dir():
            problems.append(f'{m.name}: no folder backend/modules/{m.name}/')
        for table in m.owns_tables:
            owner = TABLE_OWNER.get(table)
            if owner != m.name:
                problems.append(f'{m.name}: owns {table!r}, but rules.TABLE_OWNER says its owner is {owner!r}')
        for dep in m.depends_on:
            if dep not in known:
                problems.append(f'{m.name}: depends on {dep!r}, which is not in MODULES')
            elif (m.name, dep) not in ALLOWED_EDGES:
                problems.append(f'{m.name} -> {dep} is not allowed (modular-monolith.md 4.2, rules.ALLOWED_EDGES)')
            edges.add((m.name, dep))
        for msg in m.live_messages:
            messages.setdefault(msg, []).append(m.name)
    for msg, owners in sorted(messages.items()):
        if len(set(owners)) > 1:
            problems.append(f'live message {msg!r} is declared by {sorted(set(owners))}; names must be unique')
    cycle = find_cycle(edges)
    if cycle:
        problems.append('module dependency cycle: ' + ' -> '.join(cycle))
    return problems


def check_module_list(backend: Path, modules: Iterable[ModuleManifest], toml_text: str) -> list[str]:
    """Every `modules/<x>/module.py` is in MODULES and has a `module boundary: <x>` contract; no listed ghosts."""
    listed = {m.name for m in modules}
    contracts = {c.get('name') for c in tomllib.loads(toml_text).get('tool', {}).get('importlinter', {}).get('contracts', [])}
    on_disk = {p.parent.name for p in (backend / 'modules').glob('*/module.py')}
    problems = []
    for name in sorted(on_disk - listed):
        problems.append(f'backend/modules/{name}/module.py exists but {name!r} is not in MODULES')
    for name in sorted(listed - on_disk):
        problems.append(f'{name!r} is in MODULES but backend/modules/{name}/module.py does not exist')
    for name in sorted(on_disk | listed):
        if f'module boundary: {name}' not in contracts:
            problems.append(f'no contract named "module boundary: {name}" in importlinter.toml')
    return problems


def end_state_problems(allowlist: dict, toml_text: str, backend: Path) -> list[str]:
    """At completed_step 5 the migration is done: no allowlisted debt and no legacy shims. Earlier: nothing to check."""
    if allowlist.get('completed_step', 0) < 5:
        return []
    problems = []
    if allowlist.get('sql_writes'):
        problems.append(f"allowlist.json sql_writes must be empty at step 5, has {len(allowlist['sql_writes'])}")
    contracts = tomllib.loads(toml_text).get('tool', {}).get('importlinter', {}).get('contracts', [])
    left = [(c.get('name', '?'), e) for c in contracts for e in c.get('ignore_imports', [])]
    if left:
        problems.append(f'importlinter.toml ignore_imports must be empty at step 5, has {len(left)}')
    for shim in SHIM_FILES:
        if (backend / f'{shim}.py').exists():
            problems.append(f'backend/{shim}.py must be gone at step 5')
    return problems

