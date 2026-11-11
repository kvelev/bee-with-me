"""Module manifest: what a vertical-slice module declares about itself (modular-monolith.md section 6).

A module is a folder under `backend/modules/` plus one line in `backend.modules.MODULES`. This file only holds the
data shape and the checks that need nothing but the manifest itself; the checks across modules (table owners, allowed
edges, cycles, completeness) live in `backend/tests/architecture/rules.py` and run in the test suite.
"""
from __future__ import annotations

import asyncio
import functools
import re
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass

from fastapi import APIRouter, Depends, FastAPI
from fastapi.routing import APIRoute, APIWebSocketRoute
from starlette.routing import Mount

NAME_PATTERN = re.compile(r'^[a-z][a-z_]*$')
HTTP_METHODS = frozenset({'GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS', 'WEBSOCKET', 'MOUNT'})


@dataclass(frozen=True)
class ModuleManifest:
    name: str
    owns_tables: tuple[str, ...] = ()
    reads_tables: tuple[str, ...] = ()
    depends_on: tuple[str, ...] = ()
    router: APIRouter | None = None
    tasks: tuple[Callable[[], Awaitable[None]], ...] = ()
    live_messages: tuple[str, ...] = ()
    subscriptions: tuple[tuple[str, Callable], ...] = ()
    # Routes served without the auth dependency, as (METHOD, full path). Everything else of `router` is
    # mounted behind it by `include_module_routers` (auth by default); a module has none unless it says so here.
    public_routes: tuple[tuple[str, str], ...] = ()


def _duplicates(items: tuple[str, ...]) -> list[str]:
    return sorted({i for i in items if items.count(i) > 1})


def validate_manifest(m: ModuleManifest) -> list[str]:
    """Problems found in one manifest on its own; an empty list means valid."""
    problems: list[str] = []
    # fullmatch, not match: `$` would accept a trailing newline
    if not isinstance(m.name, str) or not NAME_PATTERN.fullmatch(m.name):
        problems.append(f'name {m.name!r} must match {NAME_PATTERN.pattern}')
    label = m.name if isinstance(m.name, str) else '?'
    for field in ('owns_tables', 'reads_tables', 'depends_on', 'live_messages'):
        dups = _duplicates(getattr(m, field))
        if dups:
            problems.append(f'{label}: {field} lists {dups} more than once')
    if m.name in m.depends_on:
        problems.append(f'{label}: a module cannot depend on itself')
    both = sorted(set(m.owns_tables) & set(m.reads_tables))
    if both:
        problems.append(f'{label}: {both} are both owned and read (an owner does not list its own tables as read)')
    if any(not isinstance(msg, str) or not msg.strip() for msg in m.live_messages):
        problems.append(f'{label}: live_messages must be non-empty strings')
    for sub in m.subscriptions:
        if len(sub) != 2 or not isinstance(sub[0], str) or not sub[0] or not callable(sub[1]):
            problems.append(f'{label}: a subscription is (event name, callable), got {sub!r}')
    publics = list(m.public_routes)
    for entry in publics:
        if (not isinstance(entry, tuple) or len(entry) != 2 or entry[0] not in HTTP_METHODS
                or not isinstance(entry[1], str) or not entry[1].startswith('/')):
            problems.append(f'{label}: a public route is (METHOD, "/path") with an upper-case method, got {entry!r}')
    if len(set(map(repr, publics))) != len(publics):
        problems.append(f'{label}: public_routes lists a route more than once')
    return problems


def _route_keys(route) -> set[tuple[str, str]]:
    """(METHOD, path) pairs of one route of a module router.

    A WebSocket route has the method WEBSOCKET, a `Mount` (for example `StaticFiles`) has the method MOUNT.
    """
    path = getattr(route, 'path', None)
    if path is None:
        return set()
    if isinstance(route, Mount):
        return {('MOUNT', path)}
    methods = getattr(route, 'methods', None) or {'WEBSOCKET'}
    return {(method.upper(), path) for method in methods}


def _leaf_routes(routes: Iterable, depth: int = 0):
    """Yield (depth, type, keys) of every served route of a router, nested includes read through `effective_candidates()`.

    FastAPI 0.142 keeps `router.include_router(sub)` as one lazy `_IncludedRouter` with no path and no methods; its
    candidates carry the full prefixed path, and a non-API route (a `Mount`, a plain `Route`) sits in `starlette_route`.
    """
    for route in routes:
        if hasattr(route, 'effective_candidates'):
            yield from _leaf_routes(route.effective_candidates(), depth + 1)
            continue
        real = getattr(route, 'starlette_route', None)
        if real is not None:                       # an effective context wrapping a non-API route
            yield depth, type(real), _route_keys(real)
        else:
            original = getattr(route, 'original_route', route)
            yield depth, type(original), _route_keys(route)


def _unguardable_problems(m: ModuleManifest) -> list[str]:
    """Routes the loader cannot put behind `Depends(auth)`: only an `APIRoute` or `APIWebSocketRoute` carries it.

    A top-level route of another type must be declared in `public_routes`. Inside a nested include there is no way
    to serve it publicly, so it is always a problem there.
    """
    if m.router is None:
        return []
    public = set(m.public_routes)
    problems: list[str] = []
    for depth, kind, keys in _leaf_routes(m.router.routes):
        if issubclass(kind, (APIRoute, APIWebSocketRoute)):
            continue
        if depth == 0 and keys and keys <= public:
            continue
        for path in sorted({path for _, path in keys}):
            problems.append(f'{m.name}: {path} is a {kind.__name__}, which cannot carry the auth dependency: '
                            'serve it from an endpoint or declare it in public_routes')
    return problems


def _public_problems(m: ModuleManifest) -> list[str]:
    """A public declaration that matches no route of the router is a typo, and a typo must not pass quietly."""
    if not m.public_routes:
        return []
    if m.router is None:
        return [f'{m.name}: public_routes is set but the module has no router']
    served = set().union(*(_route_keys(r) for r in m.router.routes)) if m.router.routes else set()
    return [f'{m.name}: public route {entry!r} is not a route of its router'
            for entry in m.public_routes if isinstance(entry, tuple) and entry not in served]


def check_modules(modules: Iterable[ModuleManifest]) -> list[str]:
    """Problems of a whole module list: each manifest's own problems plus duplicated names; empty means valid."""
    modules = list(modules)
    problems: list[str] = []
    for m in modules:
        problems.extend(validate_manifest(m))
        problems.extend(_public_problems(m))
        problems.extend(_unguardable_problems(m))
    names = [m.name for m in modules]
    for name in sorted({n for n in names if names.count(n) > 1}, key=str):
        problems.append(f'module {name} is listed twice')
    return problems


def include_module_routers(app: FastAPI, modules: Iterable[ModuleManifest], *, auth: Callable) -> None:
    """Mount the router of every manifest in list order, every route behind `Depends(auth)`.

    Auth is the default: a route is anonymous only when its manifest lists it in `public_routes`. `auth` is a
    required argument (the kernel does not import `backend.auth`; `main.py` passes `get_current_user`). An invalid
    list, or a public declaration that matches no route, mounts nothing and raises.
    """
    modules = list(modules)
    problems = check_modules(modules)
    if problems:
        raise ValueError('invalid module list: ' + '; '.join(problems))
    for m in modules:
        if m.router is None:
            continue
        public = set(m.public_routes)
        for route in m.router.routes:
            keys = _route_keys(route)
            # one route per include keeps the list order; a nested include (no path of its own) is always guarded
            is_public = bool(keys) and keys <= public
            if is_public and isinstance(route, Mount):      # a mount cannot carry a dependency: served as declared
                app.mount(route.path, route.app, name=route.name)
            elif is_public and not isinstance(route, (APIRoute, APIWebSocketRoute)):
                app.router.routes.append(route)
            else:
                app.include_router(APIRouter(routes=[route]), dependencies=None if is_public else [Depends(auth)])


def start_module_tasks(modules: Iterable[ModuleManifest],
                       on_done: Callable[[asyncio.Task, str], None]) -> list[asyncio.Task]:
    """Start every background coroutine the manifests list; `on_done(task, name)` runs when one finishes."""
    tasks: list[asyncio.Task] = []
    for m in modules:
        for fn in m.tasks:
            name = f'{m.name}.{_callable_name(fn)}'
            task = asyncio.create_task(fn(), name=name)
            # functools.partial, not a lambda: a lambda in the loop would see the last name for every task
            task.add_done_callback(functools.partial(_report_done, on_done, name))
            tasks.append(task)
    return tasks


def _callable_name(fn: Callable) -> str:
    """Name of a task callable: a `functools.partial` has none of its own, an object with `__call__` has the class's."""
    while isinstance(fn, functools.partial):
        fn = fn.func
    return getattr(fn, '__name__', None) or type(fn).__name__


def _report_done(on_done: Callable[[asyncio.Task, str], None], name: str, task: asyncio.Task) -> None:
    on_done(task, name)


async def stop_module_tasks(tasks: Iterable[asyncio.Task]) -> None:
    """Cancel all module tasks and wait until they are finished (before the pool closes)."""
    tasks = list(tasks)
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
