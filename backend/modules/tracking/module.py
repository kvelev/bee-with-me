"""Manifest of the `tracking` module: the position history and the live map read. One background task (the daily position retention in `tasks.py`), no public route."""
from ...core.modules import ModuleManifest
from . import http, tasks

manifest = ModuleManifest(
    name='tracking',
    owns_tables=('location_events', 'repeater_events'),
    reads_tables=('devices', 'groups', 'sos_alerts', 'user_groups', 'users'),
    router=http.router,
    tasks=(tasks.cleanup_positions,),
    live_messages=('location_update',),
)
