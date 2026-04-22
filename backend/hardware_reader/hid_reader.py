"""
HID device reader service.

Reads raw 64-byte packets from a USB HID device (VID/PID from .env).
The device sends the same bee protocol as the LoRaWAN serial gateway;
frames are ASCII text (##...@CRC\r\n) spread across one or more HID packets.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import asyncpg

from .parser import BeeFrame, RepeaterFrame, parse_frame
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


def _vid_pid() -> tuple[int, int]:
    from ..config import settings
    return settings.hid_vendor_id, settings.hid_product_id


async def _process_frame(raw: str, conn: asyncpg.Connection) -> None:
    frame = parse_frame(raw)
    if isinstance(frame, BeeFrame):
        await _handle_bee(frame, conn)
    elif isinstance(frame, RepeaterFrame):
        await _handle_repeater(frame, conn)
    else:
        logger.debug('HID unparseable frame: %r', raw)


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
                data = dev.read(64)
                if data:
                    status['packets_received'] += 1
                    status['last_packet_at']    = datetime.now(timezone.utc).isoformat()
                    # Strip null padding and decode
                    chunk = bytes(b for b in data if b != 0).decode('ascii', errors='replace')
                    buf += chunk
                    # Extract complete frames
                    while '\n' in buf:
                        line, buf = buf.split('\n', 1)
                        line = line.strip()
                        if line:
                            await _process_frame(line, conn)
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
