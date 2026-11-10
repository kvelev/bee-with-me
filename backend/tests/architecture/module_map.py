"""Provisional map of every production backend file to its future module (vertical-slice programme)."""
from __future__ import annotations

import fnmatch
import re

# Keys are repo-relative paths below backend/ ("routers/auth.py") or "dir/**" for a whole folder.
MODULE_OF_FILE: dict[str, tuple[str, ...]] = {
    'routers/auth.py': ('identity',),
    'routers/users.py': ('people',),
    'routers/groups.py': ('teams',),
    'routers/devices.py': ('devices',),
    'routers/locations.py': ('tracking', 'sos'),
    'routers/settings.py': ('settings',),
    'routers/fire.py': ('fire',),
    'fire/**': ('fire',),
    'routers/export.py': ('reporting',),
    'routers/tiles.py': ('maps',),
    'routers/weather.py': ('weather',),
    'routers/test.py': ('simulation',),
    'simulation.py': ('simulation',),
    'routers/hardware_reader.py': ('gateway',),
    'hardware_reader/**': ('gateway',),
    'routers/ws.py': ('core',),
    'auth.py': ('identity',),
    'core/**': ('core',),
    'db/**': ('core',),
    'version.py': ('core',),
    'json_columns.py': ('core',),
    'config.py': ('core',),
    'database.py': ('core',),
    'ws.py': ('core',),
    'main.py': (),  # assembly: owned by no module
    '__init__.py': ('core',),
    'routers/__init__.py': ('core',),
    'modules/__init__.py': ('core',),
    'modules/registry.py': ('core',),
}

STEP_OF_MODULE: dict[str, int] = {
    'settings': 1, 'fire': 2, 'tracking': 3, 'sos': 3, 'gateway': 3, 'devices': 4, 'teams': 4, 'people': 4,
    'identity': 5, 'reporting': 5, 'maps': 5, 'weather': 5, 'simulation': 5, 'core': 5,
}

# Importers whose edges to a legacy shim (config, database, json_columns, ws) go with the last step
STEP_OVERRIDE: dict[str, int] = {
    'backend.main': 5,
    'backend.db': 5,
}
SHIMS = ('backend.config', 'backend.database', 'backend.json_columns', 'backend.ws')

_MODULES_RULE = re.compile(r'^modules/([a-z][a-z_]*)/')


def owners_of(rel: str) -> tuple[str, ...]:
    """Owner module(s) of a path relative to backend/ (exact key, else longest `dir/**`, else `modules/<x>/**`)."""
    rel = rel.replace('\\', '/')
    if rel in MODULE_OF_FILE:
        return MODULE_OF_FILE[rel]
    best = None
    for key in MODULE_OF_FILE:
        if key.endswith('/**') and fnmatch.fnmatch(rel, key[:-3] + '/*'):
            if best is None or len(key) > len(best):
                best = key
    if best is not None:
        return MODULE_OF_FILE[best]
    m = _MODULES_RULE.match(rel)
    if m:
        return (m.group(1),)
    raise KeyError(rel)


def _owner_step(dotted: str) -> int | None:
    """Step of the module that owns a dotted name (backend.routers.groups -> 4), None if unmapped or ownerless."""
    parts = dotted.split('.')[1:]
    for n in range(len(parts), 0, -1):
        for cand in ('/'.join(parts[:n]) + '.py', '/'.join(parts[:n]) + '/__init__.py'):
            try:
                owners = owners_of(cand)
            except KeyError:
                continue
            return max((STEP_OF_MODULE[o] for o in owners), default=None)
    return None


def step_of(importer: str, imported: str) -> int:
    """`until step N` for the edge importer -> imported: the importer's module step.

    Shim imports of main.py and db/** are step 5; main.py itself owns nothing, so its other edges follow the
    module it imports (its fire wiring goes with the fire slice).
    """
    if imported in SHIMS or imported.startswith(tuple(s + '.' for s in SHIMS)):
        for prefix, step in STEP_OVERRIDE.items():
            if importer == prefix or importer.startswith(prefix + '.'):
                return step
    own = _owner_step(importer)
    if own is None:
        own = _owner_step(imported)
    return own if own is not None else 5
