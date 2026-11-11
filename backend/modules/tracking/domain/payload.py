"""The `location_update` message, built from plain values (pure: no database, no clock)."""
from __future__ import annotations

from datetime import datetime


def location_update_payload(*, device_id, user_id, roster, groups, mgrs, latitude, longitude, altitude_m,
                            speed_knots, course_deg, battery_voltage, gnss_satellites, gnss_valid, sos_active,
                            repeater_mode, recorded_at: datetime, received_at: datetime) -> dict:
    """The 20 keys the browsers get today, in today's order. `roster` is the `users` row or None."""
    return {
        'device_id':       str(device_id),
        'user_id':         str(user_id) if user_id else None,
        'full_name':       roster['full_name'] if roster else None,
        'rank':            roster['rank'] if roster else None,
        'photo_url':       roster['photo_url'] if roster else None,
        'phone':           roster['phone'] if roster else None,
        'mgrs':            mgrs,
        'latitude':        latitude,
        'longitude':       longitude,
        'altitude_m':      altitude_m,
        'speed_knots':     speed_knots,
        'course_deg':      course_deg,
        'battery_voltage': battery_voltage,
        'gnss_satellites': gnss_satellites,
        'gnss_valid':      gnss_valid,
        'sos_active':      sos_active,
        'repeater_mode':   repeater_mode,
        # Two distinct clocks, never conflated: recorded_at is what the device's GNSS reported,
        # received_at is when this server saw it. Freshness is judged on received_at.
        'recorded_at':     recorded_at.isoformat(),
        'received_at':     received_at.isoformat(),
        'groups':          groups,
    }
