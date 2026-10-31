"""Characterisation of hid_reader._process_frame, plus the hardware-path debt as strict xfails.

Database answers come from gateway_fakes (routed by SQL text, not by call order)."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import asyncpg
import pytest

from backend.hardware_reader import hid_reader
from backend.hardware_reader.parser import make_confirm
from backend.tests.modules.gateway.gateway_fakes import (
    BEE_BODY, REPEATER_BODY, body_with, install, make_frame,
)

pytestmark = [pytest.mark.Trait("Task", "T114"), pytest.mark.asyncio]

RAW = make_frame(BEE_BODY)                                   # dev_sn 1235, event_id 884, no SOS
RAW_NEXT_EVENT = make_frame(body_with(BEE_BODY, {24: 885}))  # same device, next event
RAW_OTHER_DEVICE = make_frame(body_with(BEE_BODY, {2: 1236}))  # other device, same event_id 884
RAW_SOS = make_frame(body_with(BEE_BODY, {18: 2}))           # flags bit 0x02: SOS
REPEATER_RAW = make_frame(REPEATER_BODY)                     # dev_sn 1256, event_id 412
REPEATER_NEXT_EVENT = make_frame(body_with(REPEATER_BODY, {10: 413}))

DEVICE = {'id': 'd1', 'user_id': 'u1'}
USER = {'full_name': 'A', 'rank': 'B', 'photo_url': None, 'phone': None, 'is_active': True}


@pytest.fixture(autouse=True)
def clean_event_state():
    hid_reader.bee_last_events.clear()
    hid_reader.repeater_last_events.clear()
    yield
    hid_reader.bee_last_events.clear()
    hid_reader.repeater_last_events.clear()


@pytest.fixture()
def clock(monkeypatch):
    """Controlled hid_reader.time.monotonic (only the reader's view of the clock, not the event loop's)."""
    now = {'t': 1000.0}
    monkeypatch.setattr(hid_reader, 'time', SimpleNamespace(monotonic=lambda: now['t']))
    return now


def patch_handler(monkeypatch, name='_handle_bee', **kwargs):
    handler = AsyncMock(**kwargs)
    monkeypatch.setattr(f'backend.hardware_reader.hid_reader.{name}', handler)
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


async def test_new_event_from_same_device_within_timeout_is_handled(mock_conn, monkeypatch, clock):
    handler = patch_handler(monkeypatch)

    await hid_reader._process_frame(RAW, mock_conn)
    clock['t'] += 1.0
    second = await hid_reader._process_frame(RAW_NEXT_EVENT, mock_conn)

    assert handler.await_count == 2
    assert [c.args[0].event_id for c in handler.await_args_list] == [884, 885]
    assert second == make_confirm(2)


async def test_same_event_after_timeout_is_handled_again(mock_conn, monkeypatch, clock):
    handler = patch_handler(monkeypatch)

    await hid_reader._process_frame(RAW, mock_conn)
    clock['t'] += hid_reader.EVENT_TIMEOUT - 0.5
    await hid_reader._process_frame(RAW, mock_conn)  # still inside the window: ignored
    assert handler.await_count == 1
    clock['t'] += 1.0  # now EVENT_TIMEOUT + 0.5 after the first frame
    await hid_reader._process_frame(RAW, mock_conn)

    assert handler.await_count == 2


async def test_same_event_id_from_two_devices_is_handled_for_both(mock_conn, monkeypatch, clock):
    handler = patch_handler(monkeypatch)

    await hid_reader._process_frame(RAW, mock_conn)
    await hid_reader._process_frame(RAW_OTHER_DEVICE, mock_conn)

    assert handler.await_count == 2
    assert [c.args[0].dev_sn for c in handler.await_args_list] == [1235, 1236]
    assert [c.args[0].event_id for c in handler.await_args_list] == [884, 884]


async def test_duplicate_repeater_event_is_not_rehandled_but_still_acked(mock_conn, monkeypatch, clock):
    handler = patch_handler(monkeypatch, name='_handle_repeater')
    bee = patch_handler(monkeypatch)

    first = await hid_reader._process_frame(REPEATER_RAW, mock_conn)
    clock['t'] += 1.0
    second = await hid_reader._process_frame(REPEATER_RAW, mock_conn)

    assert handler.await_count == 1
    assert handler.await_args.args[0].dev_sn == 1256
    assert bee.await_count == 0
    assert first == second == make_confirm(100)


async def test_new_repeater_event_within_timeout_is_handled(mock_conn, monkeypatch, clock):
    handler = patch_handler(monkeypatch, name='_handle_repeater')

    await hid_reader._process_frame(REPEATER_RAW, mock_conn)
    clock['t'] += 1.0
    await hid_reader._process_frame(REPEATER_NEXT_EVENT, mock_conn)

    assert handler.await_count == 2
    assert [c.args[0].event_id for c in handler.await_args_list] == [412, 413]


async def test_unparseable_frame_returns_none(mock_conn):
    assert await hid_reader._process_frame('##garbage@1', mock_conn) is None


@pytest.mark.xfail(
    strict=True, raises=AssertionError,
    reason='fixed in step 3 (R-06, ES-23): a frame is marked seen only after it is stored',
)
async def test_failed_store_does_not_mark_the_event_seen(mock_conn, monkeypatch):
    handler = patch_handler(monkeypatch, side_effect=[asyncpg.PostgresError('boom'), None])

    # Either fix shape is accepted: the error propagates, or _process_frame swallows it and returns None
    try:
        result = await hid_reader._process_frame(RAW, mock_conn)
    except asyncpg.PostgresError:
        result = None

    assert result is None  # no ACK for a frame that was not stored
    assert 1235 not in hid_reader.bee_last_events
    # the device retransmits; this time the store succeeds and the frame is handled
    await hid_reader._process_frame(RAW, mock_conn)
    assert handler.await_count == 2


@pytest.mark.xfail(
    strict=True, raises=AssertionError,
    reason='fixed in step 3 (R-06): no ACK for a frame that was not stored',
)
async def test_unknown_device_frame_is_not_acked(mock_conn):
    # the real _handle_bee finds no device and stores nothing
    install(mock_conn, device=None)

    result = await hid_reader._process_frame(RAW, mock_conn)

    assert mock_conn.execute.call_count == 0
    assert result is None


@pytest.mark.xfail(
    strict=True, raises=AssertionError,
    reason='fixed in step 3 (modular-monolith 5.1): position, SOS and notify in one transaction',
)
async def test_bee_frame_is_stored_in_one_transaction(mock_conn):
    alert = {'id': 'a1', 'triggered_at': datetime(2024, 12, 8, tzinfo=timezone.utc)}
    sql = install(mock_conn, device=DEVICE, prev_sos=False, existing_alert=None, alert=alert, user=USER)
    sql.record_transactions(mock_conn)

    await hid_reader._process_frame(RAW_SOS, mock_conn)

    log = sql.log

    def positions(kind, fragment):
        return [i for i, (k, s) in enumerate(log) if k == kind and fragment in s]

    begins = [i for i, entry in enumerate(log) if entry == ('tx', 'begin')]
    commits = [i for i, entry in enumerate(log) if entry == ('tx', 'commit')]
    assert len(begins) == 1, log
    assert len(commits) == 1, log
    begin, commit = begins[0], commits[0]

    location_insert = positions('execute', 'INSERT INTO location_events')
    sos_insert = positions('fetchrow', 'INSERT INTO sos_alerts')
    notify = positions('execute', 'pg_notify')
    assert len(location_insert) == 1
    assert len(sos_insert) == 1
    assert len(notify) == 2  # sos_alert + location_update
    for i in location_insert + sos_insert + notify:
        assert begin < i < commit, log
