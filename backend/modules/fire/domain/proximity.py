"""
Fire alarm decisions. Pure: no I/O, `now` is passed in, so every rule is unit-testable.

Correctness rule: never miss a hotspot that is inside the radius. Distances are exact haversine;
the satellite pixel half-size is added to the radius (the fire can be anywhere in the pixel).
Leaving range uses a 1.2× hysteresis so a rescuer on the boundary doesn't flap open/closed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

EARTH_RADIUS_M = 6_371_008.8
TARGET_POSITION_MAX_AGE_MIN = 30   # keep in sync with frontend/src/lib/freshness.js LOST_MS
EXIT_HYSTERESIS = 1.2
PIXEL_HALF_SIZE_M = {'viirs': 200, 'modis': 500, 'field_report': 0}


@dataclass(frozen=True)
class Hotspot:
    id: str
    source: str
    latitude: float
    longitude: float
    acquired_at: datetime
    is_dismissed: bool = False


@dataclass(frozen=True)
class Target:
    target_type: str            # 'hq' | 'rescuer'
    device_id: str | None
    user_id: str | None
    latitude: float
    longitude: float
    received_at: datetime | None = None


@dataclass(frozen=True)
class Zone:
    id: str
    latitude: float
    longitude: float
    radius_m: int


@dataclass(frozen=True)
class OpenAlert:
    id: str
    hotspot_id: str
    target_type: str
    device_id: str | None


@dataclass(frozen=True)
class AlarmSettings:
    is_hq_alarm_enabled: bool
    is_rescuer_alarm_enabled: bool
    hq_radius_m: int
    rescuer_radius_m: int
    alarm_max_age_hours: int
    repeat_minutes: int


@dataclass(frozen=True)
class NewAlert:
    hotspot_id: str
    target_type: str
    device_id: str | None
    user_id: str | None
    distance_m: int


@dataclass
class Decisions:
    to_open: list[NewAlert]
    to_resolve: list[tuple[str, str]]
    suppressed: dict[str, str | None]
    # True when the HQ alarm is enabled, no HQ target was passed and an open HQ alert was kept open
    # because of it (BP-02: missing data is not "out of range"). The caller should log a WARNING.
    hq_missing: bool = False


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def pixel_half_size_m(source: str) -> int:
    return PIXEL_HALF_SIZE_M.get(source, 0)


def alarm_radius_m(target_type: str, source: str, settings: AlarmSettings) -> float:
    base = settings.hq_radius_m if target_type == 'hq' else settings.rescuer_radius_m
    return base + pixel_half_size_m(source)


def suppressing_zone(hotspot: Hotspot, zones: list[Zone]) -> str | None:
    for zone in zones:
        if haversine_m(hotspot.latitude, hotspot.longitude, zone.latitude, zone.longitude) <= zone.radius_m:
            return zone.id
    return None


def is_candidate(hotspot: Hotspot, settings: AlarmSettings, now: datetime) -> bool:
    return (hotspot.source != 'field_report' and not hotspot.is_dismissed
            and hotspot.acquired_at > now - timedelta(hours=settings.alarm_max_age_hours))


def _enabled(target_type: str, settings: AlarmSettings) -> bool:
    return settings.is_hq_alarm_enabled if target_type == 'hq' else settings.is_rescuer_alarm_enabled


def _fresh(target: Target, now: datetime) -> bool:
    if target.target_type == 'hq':
        return True
    return (target.received_at is not None
            and now - target.received_at <= timedelta(minutes=TARGET_POSITION_MAX_AGE_MIN))


def _distance(hotspot: Hotspot, target: Target) -> float:
    return haversine_m(hotspot.latitude, hotspot.longitude, target.latitude, target.longitude)


def _resolve_reason(alert, hotspot, known, suppressed, settings, now) -> str | None:
    """Why an open alert closes, or None to keep it open.

    Missing data never closes an alert (BP-02): an absent or stale target (rescuer position older than
    TARGET_POSITION_MAX_AGE_MIN, or no HQ position) keeps it open. Only a fresh position beyond the
    hysteresis exit threshold is 'out_of_range'; 'disabled' only when that alarm type is switched off.
    """
    if hotspot is None:
        return 'aged_out'
    if hotspot.is_dismissed:
        return 'dismissed'
    if suppressed.get(hotspot.id):
        return 'suppressed'
    if not is_candidate(hotspot, settings, now):
        return 'aged_out'
    if not _enabled(alert.target_type, settings):
        return 'disabled'
    target = known.get((alert.target_type, alert.device_id))
    if target is None or not _fresh(target, now):
        return None
    if _distance(hotspot, target) > EXIT_HYSTERESIS * alarm_radius_m(alert.target_type, hotspot.source, settings):
        return 'out_of_range'
    return None


def evaluate(hotspots: list[Hotspot], targets: list[Target], zones: list[Zone],
             open_alerts: list[OpenAlert], settings: AlarmSettings, now: datetime) -> Decisions:
    """Decide which alerts to open and which open ones to resolve.

    Preconditions (the caller guarantees them): `targets` holds the latest position per device (plus the
    HQ target if set), all datetimes are tz-aware UTC, and `zones` contains active zones only.
    A rescuer target absent from `targets` is treated like a stale one: its open alerts stay open.
    """
    by_id = {h.id: h for h in hotspots}
    known = {(t.target_type, t.device_id): t for t in targets}
    live = {key: t for key, t in known.items() if _enabled(t.target_type, settings) and _fresh(t, now)}
    suppressed = {h.id: suppressing_zone(h, zones) for h in hotspots if h.source != 'field_report'}

    to_resolve, still_open = [], set()
    hq_missing = False
    for alert in open_alerts:
        reason = _resolve_reason(alert, by_id.get(alert.hotspot_id), known, suppressed, settings, now)
        if reason:
            to_resolve.append((alert.id, reason))
        else:
            still_open.add((alert.hotspot_id, alert.target_type, alert.device_id))
            if alert.target_type == 'hq' and ('hq', None) not in known:
                hq_missing = True

    to_open = []
    for hotspot in hotspots:
        if not is_candidate(hotspot, settings, now) or suppressed.get(hotspot.id):
            continue
        for (target_type, device_id), target in live.items():
            if (hotspot.id, target_type, device_id) in still_open:
                continue
            distance = _distance(hotspot, target)
            if distance <= alarm_radius_m(target_type, hotspot.source, settings):
                to_open.append(NewAlert(hotspot.id, target_type, device_id, target.user_id, round(distance)))
    return Decisions(to_open, to_resolve, suppressed, hq_missing)
