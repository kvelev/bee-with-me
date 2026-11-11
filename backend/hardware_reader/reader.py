"""
Serial reader service.

Reads frames from the USB LoRaWAN gateway, persists them to PostgreSQL,
and fires pg_notify so the WebSocket layer pushes updates to connected clients.

Run standalone:  python -m backend.hardware_reader.reader
Or started as a background task by the FastAPI lifespan in main.py.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import asyncpg

from ..modules.sos import api as sos_api
from ..modules.tracking import api as tracking_api
from .parser import BeeFrame, RepeaterFrame, parse_frame

logger = logging.getLogger(__name__)

# Shared status — read by GET /api/serial/status
status: dict = {
    'connected':       False,
    'port':            None,
    'baud':            None,
    'last_frame_at':   None,
    'frames_received': 0,
    'error':           None,
}

RECONNECT_DELAY = 5   # seconds between reconnect attempts


async def _broadcast_status() -> None:
    try:
        from ..ws import manager
        await manager.broadcast({'type': 'serial_status', **status})
    except Exception:
        pass


def _connect_kwargs() -> dict:
    from ..core.database import connect_kwargs
    return connect_kwargs()


def _port_and_baud() -> tuple[str, int]:
    from ..config import settings
    return settings.serial_port, settings.serial_baud


# ── DB helpers ────────────────────────────────────────────────────────────────

async def _device_row(conn: asyncpg.Connection, dev_sn: int, device_type: str) -> asyncpg.Record | None:
    # Bees and repeaters have separate serial ranges: bee 10 and repeater 10 are different devices,
    # so the frame's Cmd decides which kind of row the DevSN may match.
    return await conn.fetchrow(
        'SELECT id, user_id FROM devices WHERE dev_sn = $1 AND device_type = $2 AND is_active = TRUE',
        dev_sn, device_type,
    )


async def _handle_bee(frame: BeeFrame, conn: asyncpg.Connection) -> None:
    device = await _device_row(conn, frame.dev_sn, 'bee')
    if device is None:
        logger.warning('Unknown or inactive bee dev_sn=%s — register it first', frame.dev_sn)
        return

    # A frame without a GNSS fix still proves the device is powered and in radio range, and
    # still carries a battery reading. Record it (flagged) rather than discarding the evidence —
    # "in contact, no fix" and "gone silent" call for very different responses in the field.
    # Position columns are NOT NULL, so carry the last known fix forward for the no-fix row.
    last_fix = None
    if not frame.gnss_valid:
        last_fix = await tracking_api.last_fix(conn, device['id'])
        if last_fix is None:
            logger.info(
                'Dropping no-fix frame from dev_sn=%s — no previous fix to anchor it to',
                frame.dev_sn,
            )
            return

    latitude  = frame.latitude  if frame.gnss_valid else last_fix['latitude']
    longitude = frame.longitude if frame.gnss_valid else last_fix['longitude']
    mgrs      = frame.mgrs      if frame.gnss_valid else last_fix['mgrs']

    # SOS alerts are edge-triggered: only a FALSE -> TRUE transition opens one. Read the
    # previous state before inserting this frame, otherwise an operator who resolves an alert
    # gets it reopened by the very next frame, since the device keeps asserting SOS until it
    # is physically cleared on the hardware.
    prev_sos = await tracking_api.previous_sos_flag(conn, device['id'])

    received_at = datetime.now(timezone.utc)

    await tracking_api.insert_position(
        conn,
        device_id=device['id'], user_id=device['user_id'], msg_id=frame.msg_id,
        recorded_at=frame.recorded_at, received_at=received_at,
        latitude=latitude, longitude=longitude, mgrs=mgrs,
        altitude_m=frame.altitude_m, speed_knots=frame.speed_knots, course_deg=frame.course_deg,
        gnss_satellites=frame.gnss_satellites, battery_voltage=frame.battery_voltage,
        sos_active=frame.sos_active, repeater_mode=frame.repeater_mode, raw_flags=frame.raw_flags,
        gnss_valid=frame.gnss_valid,
    )

    if frame.sos_active and not prev_sos:
        await _ensure_sos_alert(frame, device, conn)

    # Broadcast the *effective* SOS state — "is there an alert nobody has resolved yet" —
    # not the raw flag off the wire. The device keeps asserting SOS until someone physically
    # clears it on the hardware, so sending the raw flag would light the map back up on the
    # next frame after an operator resolved the alert, and again on every page reload.
    # This matches what GET /api/locations/live computes, so both paths agree.
    sos_open = await sos_api.has_open_alert(conn, device['id'])

    user_row = await tracking_api.person_of(conn, device['user_id'])
    if user_row and not user_row['is_active']:
        return

    groups = await tracking_api.groups_of(conn, device['user_id'])

    await tracking_api.publish_position(conn, tracking_api.location_update_payload(
        device_id=device['id'], user_id=device['user_id'], roster=user_row, groups=groups,
        mgrs=mgrs, latitude=latitude, longitude=longitude, altitude_m=frame.altitude_m,
        speed_knots=frame.speed_knots, course_deg=frame.course_deg, battery_voltage=frame.battery_voltage,
        gnss_satellites=frame.gnss_satellites, gnss_valid=frame.gnss_valid, sos_active=sos_open,
        repeater_mode=frame.repeater_mode, recorded_at=frame.recorded_at, received_at=received_at,
    ))


async def _ensure_sos_alert(
    frame: BeeFrame,
    device: asyncpg.Record,
    conn: asyncpg.Connection,
) -> None:
    opened = await sos_api.raise_sos(
        conn, device_id=device['id'], user_id=device['user_id'], dev_sn=frame.dev_sn,
        triggered_at=frame.recorded_at,
    )
    if opened:
        logger.warning('SOS ALERT opened for dev_sn=%s', frame.dev_sn)


async def _handle_repeater(frame: RepeaterFrame, conn: asyncpg.Connection) -> None:
    device = await _device_row(conn, frame.dev_sn, 'repeater')
    if device is None:
        logger.warning('Unknown or inactive repeater dev_sn=%s — register it first', frame.dev_sn)
        return
    await tracking_api.insert_heartbeat(conn, device['id'], frame.msg_id, frame.battery_voltage)


# ── Read loop (one connected session) ────────────────────────────────────────

async def _read_loop(reader: asyncio.StreamReader, conn: asyncpg.Connection) -> None:
    while True:
        raw_bytes = await reader.readline()
        raw = raw_bytes.decode('ascii', errors='replace').strip()
        if not raw:
            continue

        frame = parse_frame(raw)
        if isinstance(frame, BeeFrame):
            await _handle_bee(frame, conn)
        elif isinstance(frame, RepeaterFrame):
            await _handle_repeater(frame, conn)
        else:
            logger.debug('Unparseable or unknown frame: %r', raw)

        status['last_frame_at']   = datetime.now(timezone.utc).isoformat()
        status['frames_received'] += 1


# ── Main run loop (reconnects on failure) ─────────────────────────────────────

"""async def run() -> None:
    # Support standalone execution
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    if __name__ == '__main__':
        logging.basicConfig(level=logging.INFO)

    port, baud = _port_and_baud()
    status['port'] = port
    status['baud'] = baud

    while True:
        conn = None
        try:
            import serial_asyncio
            conn = await asyncpg.connect(**_connect_kwargs())
            reader, _ = await serial_asyncio.open_serial_connection(
                url=port, baudrate=baud,
            )
            status['connected'] = True
            status['error']     = None
            logger.info('Serial reader connected on %s @ %d baud', port, baud)
            await _broadcast_status()

            await _read_loop(reader, conn)

        except asyncio.CancelledError:
            logger.info('Serial reader stopped')
            break

        except Exception as exc:
            from ..core.database import redact
            msg = redact(str(exc))
            logger.warning('Serial reader error (%s) — retrying in %ds', msg, RECONNECT_DELAY)
            status['connected'] = False
            status['error']     = msg
            await _broadcast_status()

        finally:
            if conn and not conn.is_closed():
                await conn.close()

        await asyncio.sleep(RECONNECT_DELAY)

    status['connected'] = False


if __name__ == '__main__':
    asyncio.run(run())
"""
