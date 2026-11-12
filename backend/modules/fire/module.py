"""Manifest of the `fire` module: what it owns and serves; its three background tasks live in `tasks.py`. No public route."""
from ...core.modules import ModuleManifest
from . import http, tasks

manifest = ModuleManifest(
    name='fire',
    owns_tables=('fire_hotspots', 'fire_burnt_areas', 'fire_alerts', 'fire_suppression_zones'),
    reads_tables=('devices', 'location_events', 'settings', 'users'),
    router=http.router,
    tasks=(tasks.poll_feeds, tasks.alarm_loop, tasks.cleanup_fire_data),
    live_messages=('fire_data_updated', 'fire_alert', 'fire_alert_repeat', 'fire_alert_updated', 'fire_zones_updated'),
)
