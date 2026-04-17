from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Union

import mgrs as mgrs_lib

_MGRS = mgrs_lib.MGRS()


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


@dataclass
class RepeaterFrame:
    msg_id: int
    dev_sn: int
    battery_voltage: float


Frame = Union[BeeFrame, RepeaterFrame]


# ── CRC-16 (polynomial 0xACAC) ────────────────────────────────────────────────

def crc16(data: bytes, poly: int = 0xACAC) -> int:
    crc = 0x0000
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
    """Return the payload (between ## and @CRC) if CRC passes, else None."""
    raw = raw.strip()
    if not raw.startswith('##') or '@' not in raw:
        return None
    payload, crc_hex = raw[2:].rsplit('@', 1)
    try:
        expected = int(crc_hex, 16)
    except ValueError:
        return None
    if crc16(payload.encode('ascii', errors='replace')) != expected:
        return None
    return payload


# ── Field parsers ─────────────────────────────────────────────────────────────

def _parse_bee(fields: list[str]) -> BeeFrame | None:
    # ##30,MsgId,DevSN,Hour,Min,Sec,Day,Mon,Year,GNSSStatus,Lat,Lng,
    #   Speed,Satellites,Altitude,Flags,BattVol
    if len(fields) < 17:
        return None
    try:
        year = int(fields[8])
        if year < 100:
            year += 2000
        recorded_at = datetime(
            year=year,
            month=int(fields[7]),
            day=int(fields[6]),
            hour=int(fields[3]),
            minute=int(fields[4]),
            second=int(fields[5]),
            tzinfo=timezone.utc,
        )
        # GNSSStatus: ASCII 'A' or Cyrillic 'А' both mean valid
        gnss_valid = fields[9].strip() in ('A', '\u0410')
        lat = float(fields[10])
        lng = float(fields[11])
        mgrs_str = _MGRS.toMGRS(lat, lng) if gnss_valid else ''
        flags = int(fields[15])
        return BeeFrame(
            msg_id=int(fields[1]),
            dev_sn=int(fields[2]),
            recorded_at=recorded_at,
            gnss_valid=gnss_valid,
            latitude=lat,
            longitude=lng,
            mgrs=mgrs_str,
            speed_knots=float(fields[12]),
            course_deg=None,  # not present in frame despite spec mention
            gnss_satellites=int(fields[13]),
            altitude_m=int(fields[14]),
            battery_voltage=float(fields[16]),
            sos_active=bool(flags & 0x01),
            repeater_mode=bool(flags & 0x02),
            raw_flags=flags,
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


# ── Public entry point ────────────────────────────────────────────────────────

def parse_frame(raw: str) -> Frame | None:
    payload = _strip_and_verify(raw)
    if payload is None:
        return None
    fields = payload.split(',')
    if not fields or not fields[0].isdigit():
        return None
    cmd = int(fields[0])
    if cmd == 30:
        return _parse_bee(fields)
    if cmd == 20:
        return _parse_repeater(fields)
    return None
