"""The `location_update` message, built from plain values (pure: no database, no clock).

The message is the position data (`PositionFix`, 15 keys) plus, while LIVE_PERSONAL_FIELDS is on, the personal part
(`PersonalDetails`, 5 keys). With both the result is exactly the message the browsers have always got (20 keys, same
order); without the personal part it is the thin message. PersonalDetails and the switch go away together once nothing
outside the browser is known to read the names from /ws (T547 follow-up).
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class PositionFix:
    """The 15 keys of the thin message, in the order they are sent."""
    device_id: object
    user_id: object
    mgrs: str | None
    latitude: float | None
    longitude: float | None
    altitude_m: object
    speed_knots: object
    course_deg: object
    battery_voltage: object
    gnss_satellites: object
    gnss_valid: bool
    sos_active: bool
    repeater_mode: bool
    recorded_at: datetime
    received_at: datetime


@dataclass(frozen=True)
class PersonalDetails:
    """What the full message adds about the person: five keys (`groups` is a list of team dicts)."""
    full_name: str | None
    rank: str | None
    phone: str | None
    photo_url: str | None
    groups: list


# One source of truth for "which keys of a live message are personal".
PERSONAL_KEYS = frozenset(f.name for f in dataclasses.fields(PersonalDetails))


def location_update_payload(fix: PositionFix | None = None, personal: PersonalDetails | None = None, *,
                            roster=None, groups=None, **position) -> dict:
    """The message for `fix`; `personal=None` gives the thin one, a PersonalDetails the full one.

    Legacy form, kept until the follow-up PR removes PersonalDetails: `roster` (the `users` row or None), `groups` and
    the position fields as keywords build a full message (T541 tests call it this way)."""
    if fix is None:
        fix = PositionFix(**position)
        personal = PersonalDetails(
            full_name=roster['full_name'] if roster else None, rank=roster['rank'] if roster else None,
            phone=roster['phone'] if roster else None, photo_url=roster['photo_url'] if roster else None,
            groups=groups)
    out = {
        'device_id':       str(fix.device_id),
        'user_id':         str(fix.user_id) if fix.user_id else None,
    }
    if personal is not None:
        out['full_name'] = personal.full_name
        out['rank'] = personal.rank
        out['photo_url'] = personal.photo_url
        out['phone'] = personal.phone
    out.update({
        'mgrs':            fix.mgrs,
        'latitude':        fix.latitude,
        'longitude':       fix.longitude,
        'altitude_m':      fix.altitude_m,
        'speed_knots':     fix.speed_knots,
        'course_deg':      fix.course_deg,
        'battery_voltage': fix.battery_voltage,
        'gnss_satellites': fix.gnss_satellites,
        'gnss_valid':      fix.gnss_valid,
        'sos_active':      fix.sos_active,
        'repeater_mode':   fix.repeater_mode,
        # Two distinct clocks, never conflated: recorded_at is what the device's GNSS reported,
        # received_at is when this server saw it. Freshness is judged on received_at.
        'recorded_at':     fix.recorded_at.isoformat(),
        'received_at':     fix.received_at.isoformat(),
    })
    if personal is not None:
        out['groups'] = personal.groups
    return out
