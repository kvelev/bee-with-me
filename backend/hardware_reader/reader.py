"""
Serial reader service.

Reads frames from the USB LoRaWAN gateway, persists them to PostgreSQL,
and fires pg_notify so the WebSocket layer pushes updates to connected clients.

Run standalone:  python -m backend.hardware_reader.reader
Or started as a background task by the FastAPI lifespan in main.py.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

import asyncpg

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


def _dsn() -> str:
    from ..config import settings
    return (
        f"postgresql://{settings.postgres_user}"
        f":{settings.postgres_password}"
        f"@{settings.postgres_host}"
        f":{settings.postgres_port}"
        f"/{settings.postgres_db}"
    )


def _port_and_baud() -> tuple[str, int]:
    from ..config import settings
    return settings.serial_port, settings.serial_baud


# ── DB helpers ────────────────────────────────────────────────────────────────

async def _device_row(conn: asyncpg.Connection, dev_sn: int) -> asyncpg.Record | None:
    return await conn.fetchrow(
        'SELECT id, user_id FROM devices WHERE dev_sn = $1 AND is_active = TRUE',
        dev_sn,
    )


async def _handle_bee(frame: BeeFrame, conn: asyncpg.Connection) -> None:
    device = await _device_row(conn, frame.dev_sn)
    if device is None:
        logger.warning('Unknown or inactive device dev_sn=%s — register it first', frame.dev_sn)
        return

    # A frame without a GNSS fix still proves the device is powered and in radio range, and
    # still carries a battery reading. Record it (flagged) rather than discarding the evidence —
    # "in contact, no fix" and "gone silent" call for very different responses in the field.
    # Position columns are NOT NULL, so carry the last known fix forward for the no-fix row.
    last_fix = None
    if not frame.gnss_valid:
        last_fix = await conn.fetchrow(
            """
            SELECT latitude, longitude, mgrs FROM location_events
            WHERE device_id = $1 AND gnss_valid = TRUE
            ORDER BY received_at DESC LIMIT 1
            """,
            device['id'],
        )
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
    prev_sos = await conn.fetchval(
        'SELECT sos_active FROM location_events WHERE device_id = $1 ORDER BY received_at DESC LIMIT 1',
        device['id'],
    )

    received_at = datetime.now(timezone.utc)

    await conn.execute(
        """
        INSERT INTO location_events (
            device_id, user_id, msg_id, recorded_at, received_at,
            position, latitude, longitude, mgrs,
            altitude_m, speed_knots, course_deg, gnss_satellites,
            battery_voltage, sos_active, repeater_mode, raw_flags, gnss_valid
        ) VALUES (
            $1, $2, $3, $4, $5,
            ST_SetSRID(ST_MakePoint($7, $6), 4326), $6, $7, $8,
            $9, $10, $11, $12,
            $13, $14, $15, $16, $17
        )
        """,
        device['id'], device['user_id'], frame.msg_id, frame.recorded_at, received_at,
        latitude, longitude, mgrs,
        frame.altitude_m, frame.speed_knots, frame.course_deg, frame.gnss_satellites,
        frame.battery_voltage, frame.sos_active, frame.repeater_mode, frame.raw_flags,
        frame.gnss_valid,
    )

    if frame.sos_active and not prev_sos:
        await _ensure_sos_alert(frame, device, conn)

    # Broadcast the *effective* SOS state — "is there an alert nobody has resolved yet" —
    # not the raw flag off the wire. The device keeps asserting SOS until someone physically
    # clears it on the hardware, so sending the raw flag would light the map back up on the
    # next frame after an operator resolved the alert, and again on every page reload.
    # This matches what GET /api/locations/live computes, so both paths agree.
    sos_open = await conn.fetchval(
        'SELECT EXISTS(SELECT 1 FROM sos_alerts WHERE device_id = $1 AND resolved_at IS NULL)',
        device['id'],
    )

    user_row = await conn.fetchrow(
        'SELECT full_name, rank, photo_url, phone, is_active FROM users WHERE id = $1',
        device['user_id'],
    )
    if user_row and not user_row['is_active']:
        return

    group_rows = await conn.fetch("""
        SELECT g.id, g.name, g.color, ug.is_leader
        FROM user_groups ug
        JOIN groups g ON g.id = ug.group_id
        WHERE ug.user_id = $1 AND g.is_active = TRUE
    """, device['user_id'])
    groups = [
        {'id': str(r['id']), 'name': r['name'], 'color': r['color'], 'is_leader': r['is_leader']}
        for r in group_rows
    ]

    payload = json.dumps({
        'device_id':       str(device['id']),
        'user_id':         str(device['user_id']) if device['user_id'] else None,
        'full_name':       user_row['full_name'] if user_row else None,
        'rank':            user_row['rank'] if user_row else None,
        'photo_url':       user_row['photo_url'] if user_row else None,
        'phone':           user_row['phone'] if user_row else None,
        'mgrs':            mgrs,
        'latitude':        latitude,
        'longitude':       longitude,
        'altitude_m':      frame.altitude_m,
        'speed_knots':     frame.speed_knots,
        'course_deg':      frame.course_deg,
        'battery_voltage': frame.battery_voltage,
        'gnss_satellites': frame.gnss_satellites,
        'gnss_valid':      frame.gnss_valid,
        'sos_active':      sos_open,
        'repeater_mode':   frame.repeater_mode,
        # Two distinct clocks, never conflated: recorded_at is what the device's GNSS reported
        # (can be skewed or plain wrong), received_at is when this server saw it. Freshness is
        # always judged on received_at — it's the only clock we control.
        'recorded_at':     frame.recorded_at.isoformat(),
        'received_at':     received_at.isoformat(),
        'groups':          groups,
    })
    await conn.execute("SELECT pg_notify('location_update', $1)", payload)


async def _ensure_sos_alert(
    frame: BeeFrame,
    device: asyncpg.Record,
    conn: asyncpg.Connection,
) -> None:
    existing = await conn.fetchrow(
        'SELECT id FROM sos_alerts WHERE device_id = $1 AND resolved_at IS NULL',
        device['id'],
    )
    if existing is not None:
        return

    alert = await conn.fetchrow(
        """
        INSERT INTO sos_alerts (device_id, user_id, triggered_at)
        VALUES ($1, $2, $3) RETURNING id, triggered_at
        """,
        device['id'], device['user_id'], frame.recorded_at,
    )
    logger.warning('SOS ALERT opened for dev_sn=%s', frame.dev_sn)

    who = await conn.fetchrow(
        'SELECT full_name, rank FROM users WHERE id = $1', device['user_id'],
    )
    # The payload has to carry the alert id: the browser puts these straight into the SOS
    # banner, whose Resolve button posts back to /sos/{id}/resolve. Without it the button
    # posts "undefined" and the alert can never be cleared from the UI.
    await conn.execute(
        "SELECT pg_notify('sos_alert', $1)",
        json.dumps({
            'id':           str(alert['id']),
            'device_id':    str(device['id']),
            'user_id':      str(device['user_id']) if device['user_id'] else None,
            'dev_sn':       frame.dev_sn,
            'full_name':    who['full_name'] if who else None,
            'rank':         who['rank'] if who else None,
            'triggered_at': alert['triggered_at'].isoformat(),
        }),
    )


async def _handle_repeater(frame: RepeaterFrame, conn: asyncpg.Connection) -> None:
    device = await _device_row(conn, frame.dev_sn)
    if device is None:
        return
    await conn.execute(
        'INSERT INTO repeater_events (device_id, msg_id, battery_voltage) VALUES ($1, $2, $3)',
        device['id'], frame.msg_id, frame.battery_voltage,
    )


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
            conn = await asyncpg.connect(_dsn())
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
            msg = str(exc)
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
