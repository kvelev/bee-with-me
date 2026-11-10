"""Vertical-slice modules (modular-monolith.md). A module is a folder here plus one line in `registry.py`.

This file imports no module: `MODULES` is served lazily, so importing `backend.modules.<name>.api` does not import every
module's `http.py` (and `fire -> settings.api` of step 2 is not an import cycle).
"""


def __getattr__(name: str):
    if name == 'MODULES':
        from .registry import MODULES
        return MODULES
    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')
