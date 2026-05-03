from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Union

from enum import IntEnum

import mgrs as mgrs_lib

_MGRS = mgrs_lib.MGRS()


# ── Rescuer Location (RL) Commands ─────────────────────────────────────────────

class RLCommands(IntEnum):
    CONFIRM = 1
    BEE = 30
    REPEATER = 20
    

# ── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class BeeFrame:
    msg_id: int
    dev_sn: int
    recorded_at: datetime
    gnss_valid: bool
    latitude: float
    longitude: float
    mgrs: str
    speed_knots: float
    course_deg: int | None
    gnss_satellites: int
    altitude_m: int
    battery_voltage: float
    sos_active: bool
    repeater_mode: bool
    raw_flags: int
    event_id: int


@dataclass
class RepeaterFrame:
    msg_id: int
    dev_sn: int
    battery_voltage: float


Frame = Union[BeeFrame, RepeaterFrame]


# ── CRC-16 (polynomial 0x1021, init 0xFFFF) ────────────────────────────────────────────────

def crc16(data: bytes, poly: int = 0x1021, init: int = 0xFFFF) -> int:
    crc = init
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ poly
            else:
                crc <<= 1
            crc &= 0xFFFF
    return crc


# ── Frame validation ──────────────────────────────────────────────────────────

def _strip_and_verify(raw: str) -> str | None:
    """Return the payload (Computed from ## (inclusive) to @ (exclusive)) if CRC passes, else None."""
    import logging
    _log = logging.getLogger(__name__)
    raw = raw.strip()
    if not raw.startswith('##') or '@' not in raw:
        return None
    payload, crc_str = raw.rsplit('@', 1)
    try:
        expected = int(crc_str)   # device sends CRC as decimal
    except ValueError:
        return None
    computed = crc16(payload.encode('ascii', errors='replace'))
    _log.info('CRC check: expected=%d computed=%d match=%s', expected, computed, expected == computed)
    
    return None if computed != expected else payload.removeprefix('##')


# ── Field parsers ─────────────────────────────────────────────────────────────

def _parse_bee(fields: list[str]) -> BeeFrame | None:
    # ##30,MsgId,DevSN,Hour,Min,Sec,Day,Mon,Year,GNSSStatus,Lat,Lng,
    #   Speed,Course,Satellites,Altitude,Flags,BattVol,MothRxBeeRSSI,MothRxBeeSNR,BeeRxMothRSSI,BeeRxMothSNR,EventID
    if len(fields) < 20:
        return None
    try:
        year = int(fields[10])
        if year < 100:
            year += 2000
        recorded_at = datetime(
            year=year,
            month=int(fields[9]),
            day=int(fields[8]),
            hour=int(fields[3]),
            minute=int(fields[4]),
            second=int(fields[5]),
            tzinfo=timezone.utc,
        )
        # GNSSStatus: ASCII 'A' or Cyrillic 'А' both mean valid
        gnss_valid = fields[11].strip() in ('A', 'А')
        lat = float(fields[12])
        lng = float(fields[13])
        mgrs_str = _MGRS.toMGRS(lat, lng) if gnss_valid else ''
        flags = int(fields[18])
        return BeeFrame(
            msg_id=int(fields[1]),
            dev_sn=int(fields[2]),
            recorded_at=recorded_at,
            gnss_valid=gnss_valid,
            latitude=lat,
            longitude=lng,
            mgrs=mgrs_str,
            speed_knots=float(fields[14]),
            course_deg=int(fields[15]),
            gnss_satellites=int(fields[16]),
            altitude_m=int(fields[17]),
            battery_voltage=float(fields[19]),
            sos_active=bool(flags & 0x02),
            repeater_mode=bool(flags & 0x01),
            raw_flags=flags,
            event_id=int(fields[24])
        )
    except (ValueError, IndexError):
        return None


def _parse_repeater(fields: list[str]) -> RepeaterFrame | None:
    # ##20,MsgId,DevSN,BattVol
    if len(fields) < 4:
        return None
    try:
        return RepeaterFrame(
            msg_id=int(fields[1]),
            dev_sn=int(fields[2]),
            battery_voltage=float(fields[3]),
        )
    except (ValueError, IndexError):
        return None

# ── Confirm message builder ──────────────────────────────────────────────────

def make_confirm(msgid: int) -> str:
    base = f"##{RLCommands.CONFIRM},{msgid}"
    crc = crc16(base.encode("ascii"))
    return f"{base}@{crc}\r\n"

# ── Public entry point ────────────────────────────────────────────────────────

def parse_frame(raw: str) -> Frame | None:
    payload = _strip_and_verify(raw)
    if payload is None:
        return None
    fields = payload.split(',')
    if not fields or not fields[0].isdigit():
        return None
    cmd = int(fields[0])
    match cmd:
        case RLCommands.BEE:
            return _parse_bee(fields)
        case RLCommands.REPEATER:
            return _parse_repeater(fields)
    return None
