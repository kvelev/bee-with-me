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

from fastapi import APIRouter, FastAPI

NAME_PATTERN = re.compile(r'^[a-z][a-z_]*$')


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
    return problems


def check_modules(modules: Iterable[ModuleManifest]) -> list[str]:
    """Problems of a whole module list: each manifest's own problems plus duplicated names; empty means valid."""
    modules = list(modules)
    problems: list[str] = []
    for m in modules:
        problems.extend(validate_manifest(m))
    names = [m.name for m in modules]
    for name in sorted({n for n in names if names.count(n) > 1}, key=str):
        problems.append(f'module {name} is listed twice')
    return problems


def include_module_routers(app: FastAPI, modules: Iterable[ModuleManifest]) -> None:
    """Mount the router of every manifest in list order. An invalid list mounts nothing and raises."""
    modules = list(modules)
    problems = check_modules(modules)
    if problems:
        raise ValueError('invalid module list: ' + '; '.join(problems))
    for m in modules:
        if m.router is not None:
            app.include_router(m.router)


def start_module_tasks(modules: Iterable[ModuleManifest],
                       on_done: Callable[[asyncio.Task, str], None]) -> list[asyncio.Task]:
    """Start every background coroutine the manifests list; `on_done(task, name)` runs when one finishes."""
    tasks: list[asyncio.Task] = []
    for m in modules:
        for fn in m.tasks:
            name = f'{m.name}.{fn.__name__}'
            task = asyncio.create_task(fn(), name=name)
            # functools.partial, not a lambda: a lambda in the loop would see the last name for every task
            task.add_done_callback(functools.partial(_report_done, on_done, name))
            tasks.append(task)
    return tasks


def _report_done(on_done: Callable[[asyncio.Task, str], None], name: str, task: asyncio.Task) -> None:
    on_done(task, name)


async def stop_module_tasks(tasks: Iterable[asyncio.Task]) -> None:
    """Cancel all module tasks and wait until they are finished (before the pool closes)."""
    tasks = list(tasks)
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
