"""Vertical-slice modules (modular-monolith.md). Empty until step 1; the import contracts name this package.

A module is a folder here plus one line in `MODULES`. `main.py` does not read the tuple yet: step 1, when the first
module exists, wires it.
"""
from backend.core.modules import ModuleManifest

MODULES: tuple[ModuleManifest, ...] = ()
