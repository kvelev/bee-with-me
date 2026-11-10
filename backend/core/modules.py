"""Module manifest: what a vertical-slice module declares about itself (modular-monolith.md section 6).

A module is a folder under `backend/modules/` plus one line in `backend.modules.MODULES`. This file only holds the
data shape and the checks that need nothing but the manifest itself; the checks across modules (table owners, allowed
edges, cycles, completeness) live in `backend/tests/architecture/rules.py` and run in the test suite.
"""
from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from fastapi import APIRouter

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
