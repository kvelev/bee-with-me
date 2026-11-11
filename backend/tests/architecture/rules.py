"""Rules of the module architecture that are data: table owners, allowed module edges and the checks over them."""
from __future__ import annotations

import functools
import importlib
import inspect
import tomllib
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from backend.core.modules import ModuleManifest, validate_manifest
from backend.core.ws import FORWARDED_CHANNELS
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

# Production code outside the modules that must not reach into a module's private children (`module boundary: <x>`).
LEGACY_SOURCES = ('backend.routers', 'backend.fire', 'backend.hardware_reader', 'backend.simulation',
                  'backend.main', 'backend.auth', 'backend.db')


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


def _contracts_by_name(toml_text: str) -> dict[str, dict]:
    contracts = tomllib.loads(toml_text).get('tool', {}).get('importlinter', {}).get('contracts', [])
    return {c.get('name'): c for c in contracts}


def _private_children(module_dir: Path) -> set[str]:
    """Names of the importable children of a module other than `api` and `__init__` (no `__pycache__`)."""
    names = set()
    for p in module_dir.iterdir():
        if p.is_file() and p.suffix == '.py':
            names.add(p.stem)
        elif p.is_dir() and (p / '__init__.py').is_file():
            names.add(p.name)
    return names - {'api', '__init__'}


def check_boundary_contracts(toml_text: str, module_names: Iterable[str], backend: Path) -> list[str]:
    """Each module has a `module boundary: <name>` contract that matches what is on disk.

    It must forbid every private child of the module (not `api`), and its sources must be every legacy package and
    every other module, so a new file or a new module cannot slip past the contract.
    """
    names = list(module_names)
    contracts = _contracts_by_name(toml_text)
    problems: list[str] = []
    for name in names:
        label = f'module boundary: {name}'
        contract = contracts.get(label)
        if contract is None:
            problems.append(f'no contract named "{label}" in importlinter.toml')
            continue
        if contract.get('type') != 'forbidden':
            problems.append(f'"{label}" must be of type forbidden, is {contract.get("type")!r}')
            continue
        module_dir = backend / 'modules' / name
        want_forbidden = {f'backend.modules.{name}.{c}' for c in _private_children(module_dir)} if module_dir.is_dir() else set()
        got_forbidden = set(contract.get('forbidden_modules', []))
        if got_forbidden != want_forbidden:
            problems.append(f'"{label}": forbidden_modules differ from the private children on disk; '
                            f'missing {sorted(want_forbidden - got_forbidden)}, extra {sorted(got_forbidden - want_forbidden)}')
        want_sources = set(LEGACY_SOURCES) | {f'backend.modules.{o}' for o in names if o != name}
        missing = sorted(want_sources - set(contract.get('source_modules', [])))
        if missing:
            problems.append(f'"{label}": source_modules lack {missing}')
        # B95: without allow_indirect_imports = true the contract also fails on legal chains (a legacy file imports
        # `api`, which imports a private child); import-linter's default is false.
        if contract.get('allow_indirect_imports') is not True:
            problems.append(f'"{label}": allow_indirect_imports must be true (import-linter defaults to false, '
                            f'which flags imports through the public api)')
        problems += _ignore_import_problems(label, contract, name, want_forbidden)
    return problems


def _ignore_import_problems(label: str, contract: dict, name: str, private: set[str]) -> list[str]:
    """ignore_imports of a boundary contract may only open one edge: a source into this module's own private child."""
    problems: list[str] = []
    sources = list(contract.get('source_modules', []))
    for entry in contract.get('ignore_imports', []):
        importer, arrow, imported = (part.strip() for part in str(entry).partition('->'))
        if not arrow or '*' in entry:
            problems.append(f'"{label}": ignore_imports entry {entry!r} must be "<importer> -> <imported>" without wildcards')
        elif imported not in private:
            problems.append(f'"{label}": ignore_imports entry {entry!r} may only open an import into a private child of '
                            f'backend.modules.{name} ({sorted(private)})')
        elif not any(importer == src or importer.startswith(src + '.') for src in sources):
            problems.append(f'"{label}": ignore_imports entry {entry!r} must start in one of the source_modules of the contract')
    return problems


def check_manifest_wiring(manifests: Iterable[ModuleManifest], backend: Path) -> list[str]:
    """What a manifest points at is what the folder holds: its http router, known live messages, its own tasks."""
    problems: list[str] = []
    for m in manifests:
        has_http = (backend / 'modules' / m.name / 'http.py').is_file()
        if has_http:
            dotted = f'backend.modules.{m.name}.http'
            try:
                expected = importlib.import_module(dotted).router
            except Exception as exc:   # noqa: BLE001 - any import failure is the finding
                problems.append(f'{m.name}: cannot read the router of {dotted}: {exc!r}')
            else:
                if m.router is not expected:
                    problems.append(f'{m.name}: manifest.router is not the `router` of {dotted}')
        elif m.router is not None:
            problems.append(f'{m.name}: manifest.router is set but backend/modules/{m.name}/http.py does not exist')
        for msg in m.live_messages:
            if msg not in FORWARDED_CHANNELS:
                problems.append(f'{m.name}: live message {msg!r} is not in backend.core.ws.FORWARDED_CHANNELS')
        tasks_module = f'backend.modules.{m.name}.tasks'
        for task in m.tasks:
            inner = task
            while isinstance(inner, functools.partial):   # B95: a task with bound arguments is judged by what it wraps
                inner = inner.func
            name = getattr(inner, '__name__', None) or repr(inner)
            where = getattr(inner, '__module__', None)
            if not inspect.iscoroutinefunction(task):
                problems.append(f'{m.name}: task {name} is not a coroutine function')
            elif where != tasks_module and not (where or '').startswith(tasks_module + '.'):   # tasks.py or a tasks/ package
                problems.append(f'{m.name}: task {name} must live in {tasks_module}, is in {where}')
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



# ── auth by default ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class EffectiveRoute:
    """One served route: its full path, its methods (`WEBSOCKET` for a socket) and every dependency it reaches."""
    path: str
    methods: frozenset[str]
    calls: frozenset[Callable]
    kind: str = 'APIRoute'                      # the class name of the route; `Mount`, `Route` and so on cannot carry auth


def _dependant_calls(dependant) -> set[Callable]:
    if dependant is None:
        return set()
    found = {dependant.call} if dependant.call is not None else set()
    for sub in dependant.dependencies:
        found |= _dependant_calls(sub)
    return found


def effective_routes(routes: Iterable) -> list[EffectiveRoute]:
    """Flatten a route table the way a request meets it, in order, including `include_in_schema=False` routes.

    FastAPI 0.142 keeps an included router as one lazy `_IncludedRouter` that knows its prefix and dependencies only
    through `effective_candidates()`; earlier versions copy the routes into the app. Both shapes are read here by
    duck typing, so this is the one place that depends on the layout (not `app.openapi()`, which hides routes).
    """
    from starlette.routing import Mount, WebSocketRoute

    found: list[EffectiveRoute] = []
    for route in routes:
        if hasattr(route, 'effective_candidates'):                      # a lazy included router: look inside
            found += effective_routes(route.effective_candidates())
            continue
        target = getattr(route, 'starlette_route', None) or route         # an effective context wraps the real route
        if isinstance(target, Mount):          # listed itself (a StaticFiles app has no `routes`), then what it holds
            found.append(EffectiveRoute(path=target.path, methods=frozenset({'MOUNT'}), calls=frozenset(),
                                        kind=type(target).__name__))
            found += effective_routes(getattr(target, 'routes', None) or ())
            continue
        if hasattr(target, 'routes') and not hasattr(target, 'methods'):    # another sub-application
            found += effective_routes(target.routes)
            continue
        path = getattr(target, 'path', None)
        if path is None:
            continue
        methods = frozenset(m.upper() for m in (getattr(target, 'methods', None) or ()))
        if not methods and isinstance(target, WebSocketRoute):
            methods = frozenset({'WEBSOCKET'})
        calls = _dependant_calls(getattr(target, 'dependant', None))
        calls |= {d.dependency for d in (getattr(target, 'dependencies', None) or ())}
        found.append(EffectiveRoute(path=path, methods=methods, calls=frozenset(calls), kind=type(target).__name__))
    return found


def check_module_route_auth(app_routes: Iterable, manifests: Iterable[ModuleManifest], auth: Callable) -> list[str]:
    """Every route a module serves reaches `auth` (directly or through `require_role`) or its manifest declares it public.

    A `Mount`, a plain `Route` and a plain `WebSocketRoute` never reach `auth`: they are reported unless declared public.
    """
    served = effective_routes(app_routes)
    problems: list[str] = []
    for m in manifests:
        if m.router is None:
            continue
        public = set(m.public_routes)
        for own in effective_routes(m.router.routes):
            label = f'{"/".join(sorted(own.methods))} {own.path}'
            declared = {(meth, own.path) for meth in own.methods} <= public
            mounted = [r for r in served if r.path == own.path and r.methods == own.methods]
            if not mounted:
                problems.append(f'{m.name}: {label} is not mounted in the app')
            for r in mounted:
                if own.kind not in ('APIRoute', 'APIWebSocketRoute'):
                    if not declared:
                        problems.append(f'{m.name}: {own.path} ({own.kind}) is served without the auth dependency')
                elif auth not in r.calls and not declared:
                    problems.append(f'{m.name}: {label} has no auth dependency and is not declared in public_routes')
    return problems
