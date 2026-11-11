"""
Pure GeoJSON → row conversion for the GWIS feeds. No I/O.

Untrusted upstream data: every feature is validated on its own and dropped when malformed, so one
bad feature never loses the rest of the feed. Only a response that is not a FeatureCollection at
all raises (FeedFormatError) — the caller then keeps the previous data and reports an error.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

BBOX = (41.2, 22.3, 44.3, 28.7)          # lat_min, lon_min, lat_max, lon_max (Bulgaria + border areas)
LIVE_MAX_AGE = timedelta(hours=48)
MAX_FUTURE_SKEW = timedelta(hours=1)     # device/upstream clock skew tolerated; beyond it a detection is bogus
MAX_TEXT_LEN = 256                       # stored upstream text: a longer id would break the UNIQUE btree entry
MAX_AREA_HA = 3.4e38                     # area_ha is REAL (float32): asyncpg raises above this

logger = logging.getLogger(__name__)


class FeedFormatError(ValueError):
    pass


@dataclass
class ParseStats:
    """Out-parameter of the parsers: how many features arrived and why the others were dropped.

    A silent drop hides an upstream format change (renamed field, swapped axes) behind an empty map,
    so the poller reads these counts to tell "quiet week" from "feed no longer understood".
    """
    total: int = 0
    malformed: int = 0       # not an object, wrong geometry type/shape, missing or invalid id/time/coords
    out_of_bbox: int = 0
    duplicate: int = 0
    future: int = 0

    @property
    def dropped(self) -> int:
        return self.malformed + self.out_of_bbox + self.duplicate + self.future

    def dominant_reason(self) -> str:
        """Operator hint for the dominant drop reason; only meaningful when dropped > 0."""
        reasons = [(self.malformed, '(format changed?)'),
                   (self.future, '(mostly future: check the machine clock)'),
                   (self.out_of_bbox, '(mostly outside the area: axis order changed?)'),
                   (self.duplicate, '(mostly duplicates)')]
        return max(reasons, key=lambda item: item[0])[1]

    def log_dropped(self, source: str) -> None:
        if self.dropped:
            logger.warning('GWIS %s: dropped %s of %s features (malformed %s, outside bbox %s, duplicate %s, future-dated %s)',
                           source, self.dropped, self.total, self.malformed, self.out_of_bbox, self.duplicate, self.future)


@dataclass(frozen=True)
class HotspotRow:
    source: str
    effis_id: str
    acquired_at: datetime
    latitude: float
    longitude: float
    effis_class: str | None


@dataclass(frozen=True)
class BurntAreaRow:
    source: str
    effis_id: str
    effis_fire_id: str | None
    started_at: datetime | None
    ended_at: datetime | None
    area_ha: float | None
    geometry: dict


def parse_utc(value) -> datetime | None:
    """GWIS timestamps are naive strings in UTC ('2026-09-26 11:19:00')."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace(' ', 'T', 1))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (ValueError, OverflowError):   # '9999-12-31T23:59:59-01:00' overflows on conversion to UTC
        return None


def parse_number(value) -> float | None:
    """GWIS numbers arrive as strings and may be ''."""
    if value is None or isinstance(value, bool) or value == '':
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def in_bbox(latitude: float, longitude: float) -> bool:
    lat_min, lon_min, lat_max, lon_max = BBOX
    return lat_min <= latitude <= lat_max and lon_min <= longitude <= lon_max


def _features(collection) -> list:
    if (not isinstance(collection, dict) or collection.get('type') != 'FeatureCollection'
            or not isinstance(collection.get('features'), list)):
        raise FeedFormatError('upstream response is not a GeoJSON FeatureCollection')
    return collection['features']


def is_storable(text: str, max_len: int = MAX_TEXT_LEN) -> bool:
    """True when Postgres TEXT and asyncpg accept the string: no NUL, valid UTF-8 (no lone surrogate), bounded."""
    if len(text) > max_len or '\x00' in text:
        return False
    try:
        text.encode('utf-8')
    except UnicodeEncodeError:
        return False
    return True


def _id(value) -> str | None:
    """Identifier text, or None when absent or not storable (the caller skips the feature)."""
    if value is None or value == '':
        return None
    if isinstance(value, float) and not math.isfinite(value):   # sources.py turns absurd integers into NaN
        return None
    text = value if isinstance(value, str) else str(value)
    return text if is_storable(text) else None


def _class(value) -> str | None:
    """CLASS only as a string (asyncpg rejects other types for TEXT); NUL stripped; unstorable text becomes None."""
    if not isinstance(value, str):
        return None
    text = value.replace('\x00', '')
    return text if text and is_storable(text) else None


def _area_ha(value) -> float | None:
    number = parse_number(value)
    return number if number is not None and 0 <= number <= MAX_AREA_HA else None


def _dict_parts(feature):
    """(geometry, properties) when both are objects, else None: the feature is skipped, never fatal."""
    geometry, props = feature.get('geometry'), feature.get('properties')
    if not isinstance(geometry, dict) or not isinstance(props, dict):
        return None
    return geometry, props


def parse_hotspots(collection, source: str = 'viirs', now: datetime | None = None,
                   stats: ParseStats | None = None) -> list[HotspotRow]:
    now = now or datetime.now(timezone.utc)
    stats = stats if stats is not None else ParseStats()
    rows, seen = [], set()
    features = _features(collection)
    stats.total += len(features)
    for feature in features:
        try:
            parts = _dict_parts(feature) if isinstance(feature, dict) else None
            if parts is None:
                stats.malformed += 1
                continue
            geometry, props = parts
            coords = geometry.get('coordinates')
            if geometry.get('type') != 'Point' or not isinstance(coords, list) or len(coords) < 2:
                stats.malformed += 1
                continue
            longitude, latitude = parse_number(coords[0]), parse_number(coords[1])
            if longitude is None or latitude is None:
                stats.malformed += 1
                continue
            if not in_bbox(latitude, longitude):
                stats.out_of_bbox += 1
                continue
            effis_id = _id(props.get('id'))
            acquired_at = parse_utc(props.get('acq_at'))
            if effis_id is None or acquired_at is None:
                stats.malformed += 1
                continue
            if effis_id in seen:
                stats.duplicate += 1
                continue
            if acquired_at - now > MAX_FUTURE_SKEW:
                stats.future += 1
                continue
            seen.add(effis_id)
            rows.append(HotspotRow(source, effis_id, acquired_at, latitude, longitude, _class(props.get('CLASS'))))
        except (ValueError, TypeError, OverflowError):   # last line of defence: skip this feature only
            stats.malformed += 1
            continue
    stats.log_dropped(source)
    return rows


def _position(position) -> list[float] | None:
    """Normalised [lon, lat] floats, or None when the position is not usable."""
    if not isinstance(position, list) or len(position) < 2:
        return None
    lon, lat = parse_number(position[0]), parse_number(position[1])
    if lon is None or lat is None or abs(lon) > 180 or abs(lat) > 90:
        return None
    return [lon, lat]


def _ring(ring) -> list[list[float]] | None:
    if not isinstance(ring, list) or len(ring) < 4:
        return None
    points = [_position(pos) for pos in ring]
    if any(pt is None for pt in points) or points[0] != points[-1]:
        return None
    return points


def _polygons(geometry) -> list | None:
    coords = geometry.get('coordinates')
    if geometry.get('type') == 'Polygon':
        polygons = [coords]
    elif geometry.get('type') == 'MultiPolygon':
        polygons = coords
    else:
        return None
    if not isinstance(polygons, list) or not polygons:
        return None
    clean = []
    for polygon in polygons:
        if not isinstance(polygon, list) or not polygon:
            return None
        rings = [_ring(r) for r in polygon]
        if any(r is None for r in rings):
            return None
        clean.append(rings)
    return clean


def parse_burnt_areas(collection, source: str = 'viirs', stats: ParseStats | None = None) -> list[BurntAreaRow]:
    stats = stats if stats is not None else ParseStats()
    rows, seen = [], set()
    features = _features(collection)
    stats.total += len(features)
    for feature in features:
        try:
            parts = _dict_parts(feature) if isinstance(feature, dict) else None
            if parts is None:
                stats.malformed += 1
                continue
            geometry, props = parts
            polygons = _polygons(geometry)
            if polygons is None:
                stats.malformed += 1
                continue
            if not any(in_bbox(pos[1], pos[0]) for poly in polygons for ring in poly for pos in ring):
                stats.out_of_bbox += 1
                continue
            effis_id = _id(props.get('id'))
            if effis_id is None:
                stats.malformed += 1
                continue
            if effis_id in seen:
                stats.duplicate += 1
                continue
            raw_fire_id = props.get('fire_id')
            fire_id = _id(raw_fire_id)
            if fire_id is None and raw_fire_id is not None and raw_fire_id != '':
                stats.malformed += 1     # present but unstorable (NUL, lone surrogate, too long): skip the feature
                continue
            seen.add(effis_id)
            rows.append(BurntAreaRow(
                source=source,
                effis_id=effis_id,
                effis_fire_id=fire_id,
                started_at=parse_utc(props.get('initialdate')),
                ended_at=parse_utc(props.get('finaldate')),
                area_ha=_area_ha(props.get('area')),
                geometry={'type': geometry['type'],
                          'coordinates': polygons[0] if geometry['type'] == 'Polygon' else polygons},
            ))
        except (ValueError, TypeError, OverflowError):   # last line of defence: skip this feature only
            stats.malformed += 1
            continue
    stats.log_dropped(source)
    return rows


def upstream_state(rows: list[HotspotRow], now: datetime) -> str:
    """'live' when the newest detection is under 48 h old. A quiet week is not an error."""
    newest = max((r.acquired_at for r in rows if r.acquired_at - now <= MAX_FUTURE_SKEW), default=None)
    if newest is not None and now - newest < LIVE_MAX_AGE:
        return 'live'
    return 'no_recent_detections'
