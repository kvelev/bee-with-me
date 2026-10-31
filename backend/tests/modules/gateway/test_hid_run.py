"""Characterisation of hid_reader.run(): HID packet reassembly, stale-partial discard and ACK order.

The HID device, the database connection, .env loading and the sleeps are all faked; nothing
touches real hardware or PostgreSQL."""

import asyncio
import logging
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.hardware_reader import hid_reader
from backend.hardware_reader.parser import make_confirm
from backend.tests.modules.gateway.gateway_fakes import BEE_BODY, make_frame

pytestmark = [pytest.mark.Trait("Task", "T114"), pytest.mark.asyncio]

RAW = make_frame(BEE_BODY)          # '##30,2,1235,...@crc\r\n', longer than one 64-byte packet
FRAME_TEXT = RAW.strip()             # what run() hands to _process_frame
STALE = '##30,9,9999,1,4,20'         # a frame whose tail never arrived
CONFIRM = make_confirm(2)


def packet(text: str) -> list[int]:
    data = list(text.encode('ascii'))
    assert len(data) <= hid_reader.HID_BUFFER_SIZE
    return data + [0] * (hid_reader.HID_BUFFER_SIZE - len(data))


class FakeHidDevice:
    def __init__(self, script):
        self.script = list(script)
        self.reads = 0
        self.opened_with = None
        self.nonblocking = None
        self.written = []
        self.closed = False

    def open(self, vid, pid):
        self.opened_with = (vid, pid)

    def set_nonblocking(self, flag):
        self.nonblocking = flag

    def read(self, size):
        assert size == hid_reader.HID_BUFFER_SIZE
        self.reads += 1
        return self.script.pop(0) if self.script else []

    @property
    def exhausted(self):
        return not self.script

    def write(self, report):
        self.written.append(report)

    def close(self):
        self.closed = True


@pytest.fixture()
def harness(monkeypatch):
    split = 50
    assert 0 < split < len(RAW) and len(RAW) - split <= hid_reader.HID_BUFFER_SIZE
    script = [
        packet(STALE),        # partial frame, never completed
        packet(RAW[:split]),  # a new '##' starts: the stale partial must be discarded
        packet(RAW[split:]),  # rest of the frame, ends in \r\n
        [],                   # nothing more to read
    ]
    dev = FakeHidDevice(script)
    monkeypatch.setitem(sys.modules, 'hid', SimpleNamespace(device=lambda: dev))
    # run() calls load_dotenv(): keep the real .env out of the test process
    monkeypatch.setitem(sys.modules, 'dotenv', SimpleNamespace(load_dotenv=lambda *a, **kw: None))

    conn = MagicMock()
    conn.is_closed = MagicMock(return_value=False)
    conn.close = AsyncMock()
    connect = AsyncMock(return_value=conn)
    monkeypatch.setattr(hid_reader.asyncpg, 'connect', connect)
    monkeypatch.setattr(hid_reader, '_dsn', lambda: 'postgresql://fake')
    monkeypatch.setattr(hid_reader, '_vid_pid', lambda: (0x1234, 0x5678))
    monkeypatch.setattr(hid_reader, '_broadcast_status', AsyncMock())

    order = []

    async def process(raw, c):
        order.append(('process', raw))
        return CONFIRM

    async def send(d, text):
        order.append(('send', text))

    process_frame = AsyncMock(side_effect=process)
    send_data = AsyncMock(side_effect=send)
    monkeypatch.setattr(hid_reader, '_process_frame', process_frame)
    monkeypatch.setattr(hid_reader, '_send_data', send_data)

    async def sleep(delay):
        # The read loop sleeps after every poll; stop the reader once the script is used up.
        if dev.exhausted:
            raise asyncio.CancelledError

    # Only the reader's view of asyncio is replaced, not the event loop's
    monkeypatch.setattr(hid_reader, 'asyncio', SimpleNamespace(sleep=sleep, CancelledError=asyncio.CancelledError))
    monkeypatch.setattr(hid_reader, 'status', {
        'connected': False, 'vid': None, 'pid': None,
        'last_packet_at': None, 'packets_received': 0, 'error': None,
    })
    return SimpleNamespace(
        dev=dev, conn=conn, connect=connect, order=order,
        process_frame=process_frame, send_data=send_data, script_len=len(script),
    )


async def test_split_frame_is_reassembled_and_processed_once(harness):
    await hid_reader.run()

    assert harness.process_frame.await_count == 1
    raw, conn = harness.process_frame.await_args.args
    assert raw == FRAME_TEXT
    assert conn is harness.conn


async def test_confirm_is_sent_after_the_frame_is_processed(harness):
    await hid_reader.run()

    assert harness.send_data.await_count == 1
    assert harness.send_data.await_args.args == (harness.dev, CONFIRM)
    assert harness.order == [('process', FRAME_TEXT), ('send', CONFIRM)]


async def test_stale_partial_frame_is_discarded_not_processed(harness, caplog):
    caplog.set_level(logging.WARNING, logger=hid_reader.__name__)

    await hid_reader.run()

    discarded = [r for r in caplog.records if 'discarding partial frame' in r.getMessage()]
    assert len(discarded) == 1
    assert STALE in discarded[0].getMessage()
    assert all(STALE not in call.args[0] for call in harness.process_frame.await_args_list)


async def test_packet_counter_counts_non_empty_reads(harness):
    await hid_reader.run()

    assert harness.dev.reads == harness.script_len
    assert hid_reader.status['packets_received'] == 3
    assert hid_reader.status['last_packet_at'] is not None
    assert hid_reader.status['error'] is None


async def test_device_opened_nonblocking_and_released_on_stop(harness):
    await hid_reader.run()

    assert harness.dev.opened_with == (0x1234, 0x5678)
    assert harness.dev.nonblocking is True
    assert harness.connect.await_args.args == ('postgresql://fake',)
    assert harness.dev.closed is True
    harness.conn.close.assert_awaited_once()
    assert hid_reader.status['connected'] is False
