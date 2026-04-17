"""
Serial reader service.

Reads frames from the USB LoRaWAN device, persists them to PostgreSQL,
and fires pg_notify('location_update', device_id) so the FastAPI
WebSocket layer can push updates to connected clients.

Run standalone:  python -m backend.serial.reader
Or imported as a background task by the FastAPI app.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os

import asyncpg
import serial_asyncio

from .parser import BeeFrame, RepeaterFrame, parse_frame

logger = logging.getLogger(__name__)

SERIAL_PORT = os.getenv('SERIAL_PORT', '/dev/ttyUSB0')
SERIAL_BAUD = int(os.getenv('SERIAL_BAUD', '9600'))


def _dsn() -> str:
    return (
        f"postgresql://{os.getenv('POSTGRES_USER')}"
        f":{os.getenv('POSTGRES_PASSWORD')}"
        f"@{os.getenv('POSTGRES_HOST', 'localhost')}"
        f":{os.getenv('POSTGRES_PORT', '5432')}"
        f"/{os.getenv('POSTGRES_DB')}"
    )


# ── DB helpers ────────────────────────────────────────────────────────────────

async def _device_row(conn: asyncpg.Connection, dev_sn: int) -> asyncpg.Record | None:
    return await conn.fetchrow(
        'SELECT id, user_id FROM devices WHERE dev_sn = $1 AND is_active = TRUE',
        dev_sn,
    )


async def _handle_bee(frame: BeeFrame, conn: asyncpg.Connection) -> None:
    if not frame.gnss_valid:
        logger.debug('Skipping frame with invalid GNSS fix (dev_sn=%s)', frame.dev_sn)
        return

    device = await _device_row(conn, frame.dev_sn)
    if device is None:
        logger.warning('Unknown or inactive device dev_sn=%s — register it first', frame.dev_sn)
        return

    await conn.execute(
        """
        INSERT INTO location_events (
            device_id, user_id, msg_id, recorded_at,
            position, latitude, longitude, mgrs,
            altitude_m, speed_knots, gnss_satellites,
            battery_voltage, sos_active, repeater_mode, raw_flags
        ) VALUES (
            $1, $2, $3, $4,
            ST_SetSRID(ST_MakePoint($6, $5), 4326), $5, $6, $7,
            $8, $9, $10,
            $11, $12, $13, $14
        )
        """,
        device['id'], device['user_id'], frame.msg_id, frame.recorded_at,
        frame.latitude, frame.longitude, frame.mgrs,
        frame.altitude_m, frame.speed_knots, frame.gnss_satellites,
        frame.battery_voltage, frame.sos_active, frame.repeater_mode, frame.raw_flags,
    )

    if frame.sos_active:
        await _ensure_sos_alert(frame, device, conn)

    # Fetch user info; skip broadcast for inactive users
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
        'mgrs':            frame.mgrs,
        'latitude':        frame.latitude,
        'longitude':       frame.longitude,
        'altitude_m':      frame.altitude_m,
        'speed_knots':     frame.speed_knots,
        'battery_voltage': frame.battery_voltage,
        'gnss_satellites': frame.gnss_satellites,
        'sos_active':      frame.sos_active,
        'repeater_mode':   frame.repeater_mode,
        'recorded_at':     frame.recorded_at.isoformat(),
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
    if existing is None:
        await conn.execute(
            'INSERT INTO sos_alerts (device_id, user_id, triggered_at) VALUES ($1, $2, $3)',
            device['id'], device['user_id'], frame.recorded_at,
        )
        logger.warning('SOS ALERT opened for dev_sn=%s', frame.dev_sn)
        await conn.execute(
            "SELECT pg_notify('sos_alert', $1)",
            json.dumps({'device_id': str(device['id'])}),
        )


async def _handle_repeater(frame: RepeaterFrame, conn: asyncpg.Connection) -> None:
    device = await _device_row(conn, frame.dev_sn)
    if device is None:
        return
    await conn.execute(
        'INSERT INTO repeater_events (device_id, msg_id, battery_voltage) VALUES ($1, $2, $3)',
        device['id'], frame.msg_id, frame.battery_voltage,
    )


# ── Main read loop ────────────────────────────────────────────────────────────

async def run() -> None:
    from dotenv import load_dotenv
    load_dotenv()

    conn = await asyncpg.connect(_dsn())
    logger.info('Connected to PostgreSQL')

    reader, _ = await serial_asyncio.open_serial_connection(
        url=SERIAL_PORT, baudrate=SERIAL_BAUD
    )
    logger.info('Serial reader started on %s @ %s baud', SERIAL_PORT, SERIAL_BAUD)

    while True:
        try:
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

        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception('Error processing serial frame')

    await conn.close()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())
