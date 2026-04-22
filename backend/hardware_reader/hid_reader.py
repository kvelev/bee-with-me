"""
HID device reader service.

Reads raw 64-byte packets from a USB HID device (VID/PID from .env).
Extend _handle_packet() with a parser once the device protocol is known.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

status: dict = {
    'connected':        False,
    'vid':              None,
    'pid':              None,
    'last_packet_at':   None,
    'packets_received': 0,
    'error':            None,
}

READ_INTERVAL  = 0.2   # seconds between polls
RECONNECT_DELAY = 5    # seconds between reconnect attempts


def _vid_pid() -> tuple[int, int]:
    from ..config import settings
    return settings.hid_vendor_id, settings.hid_product_id


def _handle_packet(data: list[int]) -> None:
    """Process a raw HID packet. Replace with real parsing when protocol is known."""
    logger.debug('HID packet (%d bytes): %s', len(data), data)


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
        try:
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
                    _handle_packet(data)
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

        await asyncio.sleep(RECONNECT_DELAY)

    status['connected'] = False


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    asyncio.run(run())
