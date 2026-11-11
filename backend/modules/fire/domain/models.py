"""Response shapes for the fire feature, shared by REST and WebSocket payloads."""

from __future__ import annotations

import json
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

HQ_DISTANCE_STEP_M = 100


def iso(value) -> str | None:
    return value.isoformat() if isinstance(value, datetime) else value


def hotspot_state(row) -> str:
    get = row.get if isinstance(row, dict) else (lambda k: row[k] if k in row.keys() else None)
    if get('dismissed_at'):
        return 'dismissed'
    if get('extinguished_at'):
        return 'extinguished'
    if get('suppressed_by_zone_id'):
        return 'suppressed'
    return 'active'


def hotspot_feature(row) -> dict:
    row = dict(row)
    return {
        'type': 'Feature',
        'id': str(row['id']),
        'geometry': {'type': 'Point', 'coordinates': [row['longitude'], row['latitude']]},
        'properties': {
            'id': str(row['id']),
            'source': row['source'],
            'acquired_at': iso(row['acquired_at']),
            'effis_class': row.get('effis_class'),
            'state': hotspot_state(row),
            'notes': row.get('notes'),
            'dismiss_notes': row.get('dismiss_notes'),
            'reported_device_id': str(row['reported_device_id']) if row.get('reported_device_id') else None,
        },
    }


def burnt_area_feature(row) -> dict:
    row = dict(row)
    geometry = row['geometry']
    if isinstance(geometry, str):
        geometry = json.loads(geometry)   # asyncpg returns jsonb as text unless a codec is set
    return {
        'type': 'Feature',
        'id': str(row['id']),
        'geometry': geometry,
        'properties': {
            'id': str(row['id']),
            'effis_fire_id': row.get('effis_fire_id'),
            'started_at': iso(row.get('started_at')),
            'ended_at': iso(row.get('ended_at')),
            'area_ha': row.get('area_ha'),
        },
    }


# Who is named on an alert: while it is open, the device's CURRENT holder (devices.user_id), because the person in
# danger is whoever carries the device now; a resolved alert, or a device without a holder, keeps the user the alert
# was raised for (fire_alerts.user_id).
ALERT_OUT_SELECT = """
    SELECT a.id, a.target_type::text AS target_type, a.device_id, u.id AS user_id, u.full_name, u.rank,
           a.distance_m, a.triggered_at, a.acknowledged_at, a.resolved_at,
           a.resolve_reason::text AS resolve_reason,
           h.id AS hotspot_id, h.latitude, h.longitude, h.acquired_at, h.source::text AS source
    FROM fire_alerts a
    JOIN fire_hotspots h ON h.id = a.hotspot_id
    LEFT JOIN devices d ON d.id = a.device_id
    LEFT JOIN users u ON u.id = CASE WHEN a.resolved_at IS NULL AND d.user_id IS NOT NULL
                                     THEN d.user_id ELSE a.user_id END
"""


class FireAlertHotspotOut(BaseModel):
    id: UUID
    latitude: float
    longitude: float
    acquired_at: datetime
    source: str


class FireAlertOut(BaseModel):
    """One shape for REST (GET /api/fire/alerts) and WebSocket (fire_alert, fire_alert_updated).

    Carries the rescuer's name and rank (the operator needs them) but never a phone, a photo path or the HQ position.
    The distance of an HQ alert is rounded to the nearest 100 m on output (the DB keeps the exact value), so that
    unauthenticated /ws listeners cannot trilaterate the HQ position from several alerts; rescuer alerts keep metres.
    """
    id: UUID
    target_type: str
    device_id: UUID | None
    user_id: UUID | None
    full_name: str | None
    rank: str | None
    hotspot: FireAlertHotspotOut
    distance_m: int
    triggered_at: datetime
    acknowledged_at: datetime | None
    resolved_at: datetime | None
    resolve_reason: str | None

    @classmethod
    def from_row(cls, row) -> 'FireAlertOut':
        r = dict(row)
        distance_m = r['distance_m']
        if r['target_type'] == 'hq':
            distance_m = (distance_m + HQ_DISTANCE_STEP_M // 2) // HQ_DISTANCE_STEP_M * HQ_DISTANCE_STEP_M
        return cls(
            id=r['id'], target_type=r['target_type'], device_id=r['device_id'], user_id=r['user_id'],
            full_name=r['full_name'], rank=r['rank'], distance_m=distance_m,
            triggered_at=r['triggered_at'], acknowledged_at=r['acknowledged_at'],
            resolved_at=r['resolved_at'], resolve_reason=r['resolve_reason'],
            hotspot=FireAlertHotspotOut(id=r['hotspot_id'], latitude=r['latitude'], longitude=r['longitude'],
                                        acquired_at=r['acquired_at'], source=r['source']),
        )


def zone_out(row) -> dict:
    row = dict(row)
    return {
        'id': str(row['id']),
        'label': row['label'],
        'latitude': row['latitude'],
        'longitude': row['longitude'],
        'radius_m': row['radius_m'],
        'is_active': row['is_active'],
        'disabled_at': iso(row.get('disabled_at')),
        'notes': row.get('notes'),
        'created_at': iso(row.get('created_at')),
        'updated_at': iso(row.get('updated_at')),
    }
