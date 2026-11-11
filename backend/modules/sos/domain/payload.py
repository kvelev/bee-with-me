"""The `sos_alert` message, built from plain values (pure: no database, no clock).

Five keys of ids and times (`SosAlert`) plus, while LIVE_PERSONAL_FIELDS is on, the name and rank (`SosPerson`) in the
place they have always had (between `dev_sn` and `triggered_at`). Both go away with the switch (T547 follow-up).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SosAlert:
    id: object
    device_id: object
    user_id: object
    dev_sn: object
    triggered_at: object          # a datetime


@dataclass(frozen=True)
class SosPerson:
    full_name: str | None
    rank: str | None


def sos_alert_payload(alert: SosAlert, person: SosPerson | None = None) -> dict:
    out = {
        'id':        str(alert.id),
        'device_id': str(alert.device_id),
        'user_id':   str(alert.user_id) if alert.user_id else None,
        'dev_sn':    alert.dev_sn,
    }
    if person is not None:
        out['full_name'] = person.full_name
        out['rank'] = person.rank
    out['triggered_at'] = alert.triggered_at.isoformat()
    return out
