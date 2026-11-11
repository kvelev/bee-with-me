"""Manifest of the `sos` module: the open alerts and their resolution. No task, no public route."""
from ...core.modules import ModuleManifest
from . import http

manifest = ModuleManifest(
    name='sos',
    owns_tables=('sos_alerts',),
    reads_tables=('devices', 'users'),
    router=http.router,
    live_messages=('sos_alert',),
)
