"""Manifest of the `fire` module: what it owns and serves. Tasks are added by T503; no public route."""
from ...core.modules import ModuleManifest
from . import http

manifest = ModuleManifest(
    name='fire',
    owns_tables=('fire_hotspots', 'fire_burnt_areas', 'fire_alerts', 'fire_suppression_zones'),
    reads_tables=('devices', 'location_events', 'settings', 'users'),
    router=http.router,
    live_messages=('fire_data_updated', 'fire_alert', 'fire_alert_repeat', 'fire_alert_updated', 'fire_zones_updated'),
)
