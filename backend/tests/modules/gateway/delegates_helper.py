"""Runs the reader's handlers against the routed fake connection and returns every statement as (method, sql, args).

Used by test_reader_delegates.py (T542). The clock the handlers read is frozen so the recorded args are stable.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

from backend.hardware_reader import reader
from backend.hardware_reader.parser import BeeFrame, RepeaterFrame
from backend.tests.modules.gateway.gateway_fakes import install

FROZEN = datetime(2024, 12, 8, 21, 0, 0, tzinfo=timezone.utc)
RECORDED = datetime(2024, 12, 8, 20, 50, 5, tzinfo=timezone.utc)
DEVICE = {'id': 'dev-uuid-1', 'user_id': 'user-uuid-1'}
USER = {'full_name': 'Ivan Petrov', 'rank': 'Sgt', 'photo_url': None, 'phone': '+359', 'is_active': True}
ALERT = {'id': 'alert-uuid-1', 'triggered_at': RECORDED}
LAST_FIX = {'latitude': 42.1, 'longitude': 24.1, 'mgrs': '35TNH0000000000'}


class _FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return FROZEN


def bee(**over) -> BeeFrame:
    fields = dict(
        msg_id=2, dev_sn=1235, recorded_at=RECORDED, gnss_valid=True,
        latitude=42.1438409, longitude=24.7495615, mgrs='35TNH1234567890',
        speed_knots=5.0, course_deg=137, gnss_satellites=12, altitude_m=200,
        battery_voltage=3.7,
        curr_m_rx_bee_rssi=-90, curr_m_rx_bee_snr=5, prev_bee_rx_m_rssi=-90, prev_bee_rx_m_snr=5,
        sos_active=False, repeater_mode=False, raw_flags=0, event_id=884,
    )
    fields.update(over)
    return BeeFrame(**fields)


def heartbeat() -> RepeaterFrame:
    return RepeaterFrame(msg_id=100, dev_sn=1256, battery_voltage=3.4, curr_m_rx_dev_rssi=-90,
                         curr_m_rx_dev_snr=5, prev_dev_rx_m_rssi=-90, prev_dev_rx_m_snr=5, event_id=412)


# name -> (handler, frame, state of the fake connection)
CASES = {
    'fix': ('bee', bee(), dict(device=DEVICE, user=USER, prev_sos=False)),
    'no_fix_with_previous_fix': ('bee', bee(gnss_valid=False), dict(device=DEVICE, user=USER, prev_sos=False,
                                                                    last_fix=LAST_FIX)),
    'no_fix_without_previous_fix': ('bee', bee(gnss_valid=False), dict(device=DEVICE, user=USER, prev_sos=False,
                                                                       last_fix=None)),
    'rising_sos': ('bee', bee(sos_active=True), dict(device=DEVICE, user=USER, prev_sos=False, alert=ALERT)),
    'inactive_person': ('bee', bee(), dict(device=DEVICE, user={**USER, 'is_active': False}, prev_sos=False)),
    'repeater_heartbeat': ('repeater', heartbeat(), dict(device={'id': 'rep-uuid-1', 'user_id': None})),
}


async def run_case(name: str, monkeypatch) -> list[tuple]:
    kind, frame, state = CASES[name]
    conn = AsyncMock()
    routed = install(conn, **state)
    calls: list[tuple] = []

    def record(method):
        async def call(sql, *args):
            calls.append((method, ' '.join(sql.split()), args))
            return getattr(routed, method)(sql, *args)
        return call

    for method in ('fetchrow', 'fetchval', 'fetch', 'execute'):
        setattr(conn, method, record(method))
    monkeypatch.setattr(reader, 'datetime', _FrozenDatetime)
    if kind == 'bee':
        await reader._handle_bee(frame, conn)
    else:
        await reader._handle_repeater(frame, conn)
    return calls
