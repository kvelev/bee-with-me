"""
Parser unit tests — no DB or serial port required.

Run:  pytest backend/tests/test_parser.py
"""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from backend.serial.parser import BeeFrame, RepeaterFrame, crc16, parse_frame, _strip_and_verify


# ── CRC helpers ───────────────────────────────────────────────────────────────

def make_frame(payload: str) -> str:
    crc = crc16(payload.encode('ascii'))
    return f'##{payload}@{crc:04X}\r\n'


# ── CRC ───────────────────────────────────────────────────────────────────────

def test_crc_deterministic():
    assert crc16(b'30,2,1235') == crc16(b'30,2,1235')


def test_bad_crc_rejected():
    frame = make_frame('30,1,1235,20,50,5,8,12,2024,A,42.14384090,24.74956150,5,12,200,0,3.7')
    tampered = frame[:-6] + 'FFFF\r\n'
    assert _strip_and_verify(tampered) is None


# ── Bee frame (Cmd=30) ────────────────────────────────────────────────────────

BEE_PAYLOAD = '30,2,1235,20,50,5,8,12,2024,A,42.14384090,24.74956150,5,12,200,0,3.7'


@pytest.fixture()
def bee_frame() -> BeeFrame:
    raw = make_frame(BEE_PAYLOAD)
    # mgrs conversion requires the lib; patch it to isolate parser logic
    with patch('backend.serial.parser._MGRS') as mock_mgrs:
        mock_mgrs.toMGRS.return_value = '35TLF1234567890'
        result = parse_frame(raw)
    assert isinstance(result, BeeFrame)
    return result


def test_bee_basic_fields(bee_frame):
    assert bee_frame.dev_sn == 1235
    assert bee_frame.msg_id == 2
    assert bee_frame.latitude == pytest.approx(42.14384090)
    assert bee_frame.longitude == pytest.approx(24.74956150)
    assert bee_frame.speed_knots == pytest.approx(5.0)
    assert bee_frame.gnss_satellites == 12
    assert bee_frame.altitude_m == 200
    assert bee_frame.battery_voltage == pytest.approx(3.7)


def test_bee_timestamp(bee_frame):
    assert bee_frame.recorded_at == datetime(2024, 12, 8, 20, 50, 5, tzinfo=timezone.utc)


def test_bee_gnss_valid(bee_frame):
    assert bee_frame.gnss_valid is True


def test_bee_sos_off(bee_frame):
    assert bee_frame.sos_active is False
    assert bee_frame.repeater_mode is False


def test_bee_sos_on():
    payload = '30,3,1235,20,50,5,8,12,2024,A,42.14384090,24.74956150,5,12,200,1,3.7'
    raw = make_frame(payload)
    with patch('backend.serial.parser._MGRS') as mock_mgrs:
        mock_mgrs.toMGRS.return_value = '35TLF1234567890'
        frame = parse_frame(raw)
    assert isinstance(frame, BeeFrame)
    assert frame.sos_active is True
    assert frame.repeater_mode is False


def test_bee_invalid_gnss():
    payload = '30,4,1235,20,50,5,8,12,2024,V,42.0,24.0,0,0,0,0,3.5'
    raw = make_frame(payload)
    frame = parse_frame(raw)
    assert isinstance(frame, BeeFrame)
    assert frame.gnss_valid is False
    assert frame.mgrs == ''


def test_bee_2digit_year():
    payload = '30,5,1235,10,0,0,1,1,25,A,42.0,24.0,0,5,100,0,4.0'
    raw = make_frame(payload)
    with patch('backend.serial.parser._MGRS') as mock_mgrs:
        mock_mgrs.toMGRS.return_value = '35TLF0000000000'
        frame = parse_frame(raw)
    assert isinstance(frame, BeeFrame)
    assert frame.recorded_at.year == 2025


# ── Repeater frame (Cmd=20) ───────────────────────────────────────────────────

def test_repeater_frame():
    raw = make_frame('20,100,1256,3.4')
    frame = parse_frame(raw)
    assert isinstance(frame, RepeaterFrame)
    assert frame.dev_sn == 1256
    assert frame.msg_id == 100
    assert frame.battery_voltage == pytest.approx(3.4)


# ── Edge cases ────────────────────────────────────────────────────────────────

def test_missing_hash_prefix_rejected():
    assert parse_frame('30,1,1235@ABCD\r\n') is None


def test_garbage_rejected():
    assert parse_frame('not a frame at all') is None


def test_too_few_fields_rejected():
    raw = make_frame('30,1,1235,10,0')
    assert parse_frame(raw) is None
