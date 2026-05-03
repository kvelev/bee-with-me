"""
HID device reader service.

Reads raw 64-byte packets from a USB HID device (VID/PID from .env).
The device sends the same bee protocol as the LoRaWAN serial gateway;
frames are ASCII text (##...@CRC\r\n) spread across one or more HID packets.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

import asyncpg

from .parser import BeeFrame, RepeaterFrame, parse_frame, make_confirm
from .reader import _handle_bee, _handle_repeater, _dsn

logger = logging.getLogger(__name__)

status: dict = {
    'connected':        False,
    'vid':              None,
    'pid':              None,
    'last_packet_at':   None,
    'packets_received': 0,
    'error':            None,
}

READ_INTERVAL   = 0.02   # seconds between polls (50 Hz)
RECONNECT_DELAY = 5      # seconds between reconnect attempts

HID_BUFFER_SIZE = 64     # bytes per packet



def _vid_pid() -> tuple[int, int]:
    from ..config import settings
    return settings.hid_vendor_id, settings.hid_product_id


# ── Send Data ────────────────────────────────────────────────────────

async def _send_data(dev, text: str):
    data = text.encode('utf-8')

    chunk_size = HID_BUFFER_SIZE - 1  # 64 - 1 byte report ID
    for i in range(0, len(data), chunk_size):
        chunk = data[i:i+chunk_size]
        report = bytes([0x00]) + chunk

        # padding to 64 bytes
        report += bytes(HID_BUFFER_SIZE - len(report))

        dev.write(report)

# ──── Process frame ─────────────────────────────────────────────────────

EVENT_TIMEOUT = 15.0  # секунди
bee_last_events = {} # { "SN123": (event_id, timestamp) }

async def _process_frame(raw: str, conn: asyncpg.Connection) -> str | None:
    frame = parse_frame(raw)

    if not frame:
        logger.warning('HID unparseable frame: %r', raw)
        return None

    logger.info('HID parse result: %s', frame)

    if isinstance(frame, BeeFrame):
        now = time.monotonic()
        last_id, last_time = bee_last_events.get(frame.dev_sn, (None, 0))

        is_repeated = (frame.event_id == last_id) and (now - last_time < EVENT_TIMEOUT)

        if not is_repeated:
            bee_last_events[frame.dev_sn] = (frame.event_id, now) # update only if not repeated
            await _handle_bee(frame, conn)
        else:
            logger.info('Repeated BeeFrame ignored for %s', frame.dev_sn)

    elif isinstance(frame, RepeaterFrame):
        await _handle_repeater(frame, conn)

    return make_confirm(frame.msg_id)


async def run() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    import hid

    vid, pid = _vid_pid()
    status['vid'] = hex(vid)
    status['pid'] = hex(pid)

    while True:
        dev = None
        conn = None
        buf = ''
        try:
            conn = await asyncpg.connect(_dsn())
            dev = hid.device()
            dev.open(vid, pid)
            dev.set_nonblocking(True)
            status['connected'] = True
            status['error']     = None
            logger.info('HID device opened VID=%s PID=%s', hex(vid), hex(pid))

            while True:
                data = dev.read(HID_BUFFER_SIZE)
                if data:
                    status['packets_received'] += 1
                    status['last_packet_at']    = datetime.now(timezone.utc).isoformat()
                    logger.info('HID raw packet #%d: %s', status['packets_received'], list(data))
                    # Strip null padding and decode
                    chunk = bytes(b for b in data if b != 0).decode('ascii', errors='replace')
                    logger.info('HID decoded chunk: %r', chunk)
                    buf += chunk
                    # Discard any stale partial frame when a new one starts mid-buffer
                    second = buf.find('##', 2)
                    if second != -1:
                        logger.warning('HID discarding partial frame: %r', buf[:second])
                        buf = buf[second:]
                    # Extract complete frames
                    while '\n' in buf:
                        line, buf = buf.split('\n', 1)
                        line = line.strip()
                        if line:
                            logger.info('HID frame extracted: %r', line)
                            confirm = await _process_frame(line, conn)
                            if confirm:
                                logger.info('HID confirm to send: %s', confirm)
                                await _send_data(dev, confirm)
                await asyncio.sleep(READ_INTERVAL)

        except asyncio.CancelledError:
            logger.info('HID reader stopped')
            break

        except Exception as exc:
            msg = str(exc)
            logger.warning('HID reader error (%s) — retrying in %ds', msg, RECONNECT_DELAY)
            status['connected'] = False
            status['error']     = msg

        finally:
            if dev is not None:
                try:
                    dev.close()
                except Exception:
                    pass
            if conn and not conn.is_closed():
                await conn.close()

        await asyncio.sleep(RECONNECT_DELAY)

    status['connected'] = False


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    asyncio.run(run())
