from typing import Annotated
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends

from ...auth import get_current_user
from ...core.database import get_conn
from .infrastructure import repository

router = APIRouter(prefix='/api/locations', tags=['locations'])


@router.get('/sos')
async def open_sos_alerts(
    conn: Annotated[asyncpg.Connection, Depends(get_conn)],
    _: Annotated[asyncpg.Record, Depends(get_current_user)],
):
    rows = await repository.fetch_open_alerts(conn)
    return [dict(r) for r in rows]


@router.post('/sos/{alert_id}/resolve')
async def resolve_sos(
    alert_id: UUID,
    notes: str | None = None,
    conn: Annotated[asyncpg.Connection, Depends(get_conn)] = None,
    current_user: Annotated[asyncpg.Record, Depends(get_current_user)] = None,
):
    await repository.resolve_alert(conn, alert_id, current_user['id'], notes)
    return {'resolved': True}
