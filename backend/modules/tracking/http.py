from collections import defaultdict
from datetime import datetime
from typing import Annotated
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, Query

from ...auth import get_current_user
from ...core.config import settings
from ...core.database import get_conn
from ...core.json_columns import decode_json_columns
from .infrastructure import repository

router = APIRouter(prefix='/api/locations', tags=['locations'])


@router.get('/live')
async def live_positions(
    conn: Annotated[asyncpg.Connection, Depends(get_conn)],
    _: Annotated[asyncpg.Record, Depends(get_current_user)],
):
    """Latest position for every active device seen within the freshness horizon.

    Bounded by `live_position_max_age_hours` so devices from a previous operation don't
    linger on the map as ghosts indistinguishable from rescuers currently in the field.
    """
    rows = await repository.fetch_live(conn, settings.live_position_max_age_hours)
    return [decode_json_columns(r, 'groups') for r in rows]


@router.get('/trail')
async def location_trail(
    conn: Annotated[asyncpg.Connection, Depends(get_conn)],
    _: Annotated[asyncpg.Record, Depends(get_current_user)],
    minutes: int = Query(30, ge=1, le=60),
):
    """Return all location events from the last N minutes, grouped by device_id.

    Bounded by the device's current assignment (assigned_at) so a reassigned or
    unassigned device's trail doesn't splice in the previous volunteer's movement.
    """
    rows = await repository.fetch_trail(conn, minutes)
    grouped = defaultdict(list)
    for r in rows:
        grouped[str(r['device_id'])].append({
            'lat': r['latitude'],
            'lon': r['longitude'],
            'recorded_at': r['recorded_at'].isoformat(),
            'received_at': r['received_at'].isoformat(),
        })
    return dict(grouped)


@router.get('/{device_id}/history')
async def device_history(
    device_id: UUID,
    conn: Annotated[asyncpg.Connection, Depends(get_conn)],
    _: Annotated[asyncpg.Record, Depends(get_current_user)],
    from_dt: datetime | None = Query(None, alias='from'),
    to_dt: datetime | None = Query(None, alias='to'),
    limit: int = Query(500, le=5000),
    offset: int = 0,
):
    rows = await repository.fetch_history(conn, device_id, from_dt, to_dt, limit, offset)
    return [dict(r) for r in rows]
