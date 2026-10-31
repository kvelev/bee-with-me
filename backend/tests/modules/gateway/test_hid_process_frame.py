"""Characterisation of hid_reader._process_frame, plus the hardware-path debt as strict xfails."""

from unittest.mock import AsyncMock

import asyncpg
import pytest

from backend.hardware_reader import hid_reader
from backend.hardware_reader.parser import crc16, make_confirm

pytestmark = [pytest.mark.Trait("Task", "T114"), pytest.mark.asyncio]

# Valid Cmd=30 frame body (same as test_parser.BEE_BODY): msg_id 2, dev_sn 1235, event_id 884
BEE_BODY = (
    '30,2,1235,1,4,20,50,5,8,12,2024,A,42.14384090,24.74956150,'
    '5,137,12,200,0,3.7,-97,7,-101,5,884'
)


def make_frame(body: str) -> str:
    payload = f'##{body}'
    return f'{payload}@{crc16(payload.encode("ascii", errors="replace"))}\r\n'


RAW = make_frame(BEE_BODY)


@pytest.fixture(autouse=True)
def clean_event_state():
    hid_reader.bee_last_events.clear()
    hid_reader.repeater_last_events.clear()
    yield
    hid_reader.bee_last_events.clear()
    hid_reader.repeater_last_events.clear()


def patch_handler(monkeypatch, **kwargs):
    handler = AsyncMock(**kwargs)
    monkeypatch.setattr('backend.hardware_reader.hid_reader._handle_bee', handler)
    return handler


async def test_valid_bee_frame_is_handled_and_acked(mock_conn, monkeypatch):
    handler = patch_handler(monkeypatch)

    result = await hid_reader._process_frame(RAW, mock_conn)

    assert result == make_confirm(2)
    assert handler.await_count == 1
    assert handler.await_args.args[0].dev_sn == 1235
    assert handler.await_args.args[1] is mock_conn


async def test_duplicate_event_within_timeout_is_not_rehandled_but_still_acked(mock_conn, monkeypatch):
    handler = patch_handler(monkeypatch)

    first = await hid_reader._process_frame(RAW, mock_conn)
    second = await hid_reader._process_frame(RAW, mock_conn)

    assert handler.await_count == 1
    assert first == second == make_confirm(2)


async def test_unparseable_frame_returns_none(mock_conn):
    assert await hid_reader._process_frame('##garbage@1', mock_conn) is None


@pytest.mark.xfail(strict=True, reason='fixed in step 3 (R-06, ES-23): a frame is marked seen only after it is stored')
async def test_failed_store_does_not_mark_the_event_seen(mock_conn, monkeypatch):
    handler = patch_handler(monkeypatch, side_effect=asyncpg.PostgresError('boom'))

    with pytest.raises(asyncpg.PostgresError):
        await hid_reader._process_frame(RAW, mock_conn)

    assert 1235 not in hid_reader.bee_last_events
    with pytest.raises(asyncpg.PostgresError):
        await hid_reader._process_frame(RAW, mock_conn)
    assert handler.await_count == 2


@pytest.mark.xfail(strict=True, reason='fixed in step 3 (R-06): no ACK for a frame that was not stored')
async def test_unknown_device_frame_is_not_acked(mock_conn):
    # mock_conn.fetchrow returns None: the real _handle_bee finds no device and stores nothing
    result = await hid_reader._process_frame(RAW, mock_conn)

    assert result is None


@pytest.mark.xfail(strict=True, reason='fixed in step 3 (modular-monolith 5.1): position, SOS and notify in one transaction')
async def test_bee_frame_is_stored_in_one_transaction(mock_conn):
    user = {'full_name': 'A', 'rank': 'B', 'photo_url': None, 'phone': None, 'is_active': True}
    mock_conn.fetchrow = AsyncMock(side_effect=[{'id': 'd1', 'user_id': 'u1'}, user])
    mock_conn.fetchval = AsyncMock(side_effect=[False, False])

    await hid_reader._process_frame(RAW, mock_conn)

    assert mock_conn.transaction.call_count == 1
