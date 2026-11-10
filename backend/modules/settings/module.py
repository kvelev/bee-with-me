"""Manifest of the `settings` module: what it owns and serves. It has no public route and no background task."""
from ...core.modules import ModuleManifest
from . import http

manifest = ModuleManifest(name='settings', owns_tables=('settings',), router=http.router)
