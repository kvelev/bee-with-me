"""Manifest of the `tracking` module: the position history and the live map read. No task, no public route."""
from ...core.modules import ModuleManifest
from . import http

manifest = ModuleManifest(
    name='tracking',
    owns_tables=('location_events', 'repeater_events'),
    reads_tables=('devices', 'groups', 'sos_alerts', 'user_groups', 'users'),
    router=http.router,
    live_messages=('location_update',),
)
