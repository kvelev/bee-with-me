"""Manifest of the `weather` module: one router behind a login. No table, no task, no live message, no public route."""
from ...core.modules import ModuleManifest
from . import http

manifest = ModuleManifest(name='weather', router=http.router)
