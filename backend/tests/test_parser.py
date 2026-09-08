"""
Parser unit tests — no DB or serial port required.

Run:  pytest backend/tests/test_parser.py

These are written against the frame format the devices actually send (25-field Cmd=30,
11-field Cmd=20, CRC-16/CCITT-FALSE over the '##' marker, transmitted as DECIMAL). An
earlier version of this file encoded a superseded format — CRC computed without the '##'
prefix and rendered as hex, 17-field bee frames — so every frame it built was rejected by
the parser and the whole suite failed. If these tests start failing, suspect the wire
format changed and check against a real capture before touching the parser.
"""

from datetime import datetime, timezone

import pytest

from backend.hardware_reader.parser import (
    BeeFrame, RepeaterFrame, crc16, make_confirm, parse_frame, _strip_and_verify,
)


# ── Frame construction ────────────────────────────────────────────────────────

def make_frame(body: str) -> str:
    """Wrap a payload the way a device does.

    Two details that are easy to get wrong, and that the old suite got wrong:
    the CRC covers the '##' marker as well as the body, and it goes on the wire
    in DECIMAL, not hex.

    errors='replace' mirrors _strip_and_verify exactly — it matters for the Cyrillic
    GNSSStatus case, where the byte is not ASCII-encodable.
    """
    payload = f'##{body}'
    return f'{payload}@{crc16(payload.encode("ascii", errors="replace"))}\r\n'


# ##30,MsgId,DevSN,HWVer,SWVer,Hour,Min,Sec,Day,Mon,Year,GNSSStatus,Lat,Lng,Speed,Course,
#     Satellites,Altitude,Flags,BattVol,CurrMothRxBeeRSSI,CurrMothRxBeeSNR,
#     PrevBeeRxMothRSSI,PrevBeeRxMothSNR,EventID
BEE_BODY = (
    '30,2,1235,1,4,20,50,5,8,12,2024,A,42.14384090,24.74956150,'
    '5,137,12,200,0,3.7,-97,7,-101,5,884'
)

# ##20,MsgId,DevSN,HWVer,SWVer,BattVol,CurrMRxDevRSSI,CurrMRxDevSNR,
#     PrevDevRxMRSSI,PrevDevRxMSNR,EventID
REPEATER_BODY = '20,100,1256,1,4,3.4,-88,9,-92,8,412'


def bee_body(overrides: dict[int, object]) -> str:
    """BEE_BODY with individual fields swapped out, keyed by protocol field index."""
    fields = BEE_BODY.split(',')
    for idx, value in overrides.items():
        fields[idx] = str(value)
    return ','.join(fields)


# ── CRC ───────────────────────────────────────────────────────────────────────

def test_crc_is_ccitt_false():
    """Pins the algorithm identity: CRC-16/CCITT-FALSE's published check value for the
    ASCII string '123456789' is 0x29B1. If this breaks, the polynomial or the seed moved."""
    assert crc16(b'123456789') == 0x29B1


def test_crc_covers_the_hash_marker():
    body = '30,2,1235'
    assert crc16(f'##{body}'.encode()) != crc16(body.encode())


def test_crc_is_read_as_decimal_not_hex():
    payload = f'##{BEE_BODY}'
    crc = crc16(payload.encode('ascii'))
    assert _strip_and_verify(f'{payload}@{crc}\r\n') is not None
    # The same value rendered as hex is a different number, and must be rejected
    assert _strip_and_verify(f'{payload}@{crc:04X}\r\n') is None


def test_bad_crc_rejected():
    payload = f'##{BEE_BODY}'
    wrong = crc16(payload.encode('ascii')) ^ 0xFF
    assert _strip_and_verify(f'{payload}@{wrong}\r\n') is None


def test_non_numeric_crc_rejected():
    assert _strip_and_verify(f'##{BEE_BODY}@NOTANUMBER\r\n') is None


def test_strip_returns_body_without_marker():
    assert _strip_and_verify(make_frame(BEE_BODY)) == BEE_BODY


# ── Bee frame (Cmd=30) ────────────────────────────────────────────────────────

@pytest.fixture()
def bee() -> BeeFrame:
    frame = parse_frame(make_frame(BEE_BODY))
    assert isinstance(frame, BeeFrame)
    return frame


def test_bee_identity(bee):
    assert bee.msg_id == 2
    assert bee.dev_sn == 1235
    assert bee.event_id == 884


def test_bee_position(bee):
    assert bee.latitude == pytest.approx(42.14384090)
    assert bee.longitude == pytest.approx(24.74956150)
    # MGRS is computed for real here rather than mocked — it is what the operator reads
    # off the screen, so a wrong conversion should fail the suite.
    assert bee.mgrs == '35TLG1403968198'


def test_bee_telemetry(bee):
    assert bee.speed_knots == pytest.approx(5.0)
    assert bee.course_deg == 137
    assert bee.gnss_satellites == 12
    assert bee.altitude_m == 200
    assert bee.battery_voltage == pytest.approx(3.7)


def test_bee_timestamp(bee):
    assert bee.recorded_at == datetime(2024, 12, 8, 20, 50, 5, tzinfo=timezone.utc)


def test_bee_2digit_year():
    frame = parse_frame(make_frame(bee_body({10: 25})))
    assert isinstance(frame, BeeFrame)
    assert frame.recorded_at.year == 2025


def test_bee_gnss_valid(bee):
    assert bee.gnss_valid is True


def test_bee_gnss_invalid_leaves_mgrs_empty():
    frame = parse_frame(make_frame(bee_body({11: 'V'})))
    assert isinstance(frame, BeeFrame)
    assert frame.gnss_valid is False
    assert frame.mgrs == ''


def test_bee_accepts_cyrillic_a_for_valid_fix():
    """Some firmware emits Cyrillic 'А' (U+0410) instead of ASCII 'A' — visually identical,
    different codepoint. Treating it as 'no fix' would silently drop good positions."""
    frame = parse_frame(make_frame(bee_body({11: 'А'})))
    assert isinstance(frame, BeeFrame)
    assert frame.gnss_valid is True


def test_cyrillic_a_cannot_survive_the_readers_ascii_decode():
    """Documents a real gap, not desired behaviour.

    parse_frame() handles Cyrillic 'А' (test above), but neither reader can deliver it:
    both do `.decode('ascii', errors='replace')` on the bytes off the wire, which turns
    the Cyrillic byte(s) into U+FFFD before the parser is ever called. So the Cyrillic
    branch in _parse_bee is unreachable in production, and a device emitting it would be
    read as "no fix" on every frame.

    Fixing it means changing the decode in hid_reader/reader (and the matching encode in
    _strip_and_verify) to something byte-preserving like latin-1 — a change on the hot
    path that should be made against real hardware, not guessed at.
    """
    for wire_bytes in ('А'.encode('utf-8'), b'\xc0'):        # UTF-8 and CP1251 forms
        decoded = wire_bytes.decode('ascii', errors='replace')
        assert decoded.strip() not in ('A', 'А')


# Flags: bit 0 (0x01) = repeater mode, bit 1 (0x02) = SOS.
@pytest.mark.parametrize('flags, sos, repeater', [
    (0, False, False),
    (1, False, True),
    (2, True,  False),
    (3, True,  True),
])
def test_bee_flag_bits(flags, sos, repeater):
    frame = parse_frame(make_frame(bee_body({18: flags})))
    assert isinstance(frame, BeeFrame)
    assert frame.sos_active is sos
    assert frame.repeater_mode is repeater
    assert frame.raw_flags == flags


def test_bee_negative_rssi_does_not_break_parsing(bee):
    """RSSI fields are negative dBm and sit between BattVol and EventID. They aren't
    captured yet, but they must not stop the fields after them from being read."""
    assert bee.event_id == 884


# ── Repeater frame (Cmd=20) ───────────────────────────────────────────────────

def test_repeater_frame():
    frame = parse_frame(make_frame(REPEATER_BODY))
    assert isinstance(frame, RepeaterFrame)
    assert frame.msg_id == 100
    assert frame.dev_sn == 1256
    assert frame.battery_voltage == pytest.approx(3.4)
    assert frame.event_id == 412


# ── Confirm (Cmd=1) ───────────────────────────────────────────────────────────

def test_make_confirm_shape():
    assert make_confirm(24).startswith('##1,24@')
    assert make_confirm(24).endswith('\r\n')


def test_make_confirm_is_itself_a_valid_frame():
    """The ACK we send back has to pass the same CRC check the device applies."""
    assert _strip_and_verify(make_confirm(24)) == '1,24'


# ── Edge cases ────────────────────────────────────────────────────────────────

def test_missing_hash_prefix_rejected():
    assert parse_frame('30,1,1235@12345\r\n') is None


def test_missing_crc_delimiter_rejected():
    assert parse_frame(f'##{BEE_BODY}\r\n') is None


def test_garbage_rejected():
    assert parse_frame('not a frame at all') is None


def test_empty_rejected():
    assert parse_frame('') is None


def test_truncated_bee_frame_rejected():
    """24 fields — one short of EventID. A frame missing its tail must be dropped whole,
    not parsed into a position with garbage in the last field."""
    truncated = ','.join(BEE_BODY.split(',')[:24])
    assert parse_frame(make_frame(truncated)) is None


def test_truncated_repeater_frame_rejected():
    truncated = ','.join(REPEATER_BODY.split(',')[:10])
    assert parse_frame(make_frame(truncated)) is None


def test_unknown_command_rejected():
    assert parse_frame(make_frame('99,1,1235,1,4')) is None


def test_non_numeric_field_rejected():
    assert parse_frame(make_frame(bee_body({2: 'ABC'}))) is None


def test_surrounding_whitespace_tolerated():
    frame = parse_frame('  ' + make_frame(BEE_BODY))
    assert isinstance(frame, BeeFrame)
