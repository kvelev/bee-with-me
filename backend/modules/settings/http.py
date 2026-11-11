"""HTTP of the `settings` module: one request, its transaction boundaries and the reaction after it. No SQL here."""
import logging
from typing import Annotated, Callable

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status

from ...auth import get_current_user, require_role
from ...core.database import get_conn
from ..fire import api as fire_repository
from ..fire.api import notify_alerts_updated
from .api import SettingsChanged
from .domain.models import HQIn, HQPatch, SettingsOut, SettingsUpdate
from .infrastructure import publisher, repository

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/api/settings', tags=['settings'])

Conn = Annotated[asyncpg.Connection, Depends(get_conn)]


def _publish_settings_changed() -> None:
    publisher.publish(SettingsChanged())


# Called after every saved change. A module-level name so tests can replace it; the default tells fire.
after_change: Callable[[], None] | None = _publish_settings_changed


def _out(row) -> SettingsOut:
    return SettingsOut(**{k: row[k] for k in SettingsOut.model_fields})


def _changed() -> None:
    if after_change is not None:
        after_change()


def _missing() -> HTTPException:
    logger.error('settings row (id=1) is missing; restore it from a backup or re-run the migrations')
    return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail='settings_missing')


@router.get('', response_model=SettingsOut)
async def get_settings(conn: Conn, _: Annotated[asyncpg.Record, Depends(get_current_user)]):
    row = await repository.fetch_settings(conn)
    if row is None:
        raise _missing()
    return _out(row)


@router.put('', response_model=SettingsOut)
async def put_settings(body: SettingsUpdate, conn: Conn,
                       user: Annotated[asyncpg.Record, Depends(require_role('admin'))]):
    resolved: list[str] = []
    async with conn.transaction():
        row = await repository.update_settings(conn, body, user['id'])
        if row is not None and body.hq_latitude is None:
            resolved = await fire_repository.resolve_hq_alerts(conn, user['id'])
    if row is None:
        if not await repository.row_exists(conn):
            raise _missing()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='settings_stale')
    await notify_alerts_updated(conn, resolved)
    out = _out(row)
    logger.info('settings updated by user %s (hq_alarm=%s, rescuer_alarm=%s, hq_radius_m=%s, rescuer_radius_m=%s, rescuer_photo_on_map=%s)',
                user['id'], body.is_hq_alarm_enabled, body.is_rescuer_alarm_enabled,
                body.hq_radius_m, body.rescuer_radius_m, body.is_rescuer_photo_on_map_enabled)
    _changed()
    return out


@router.put('/hq', response_model=SettingsOut)
async def put_hq(body: HQPatch, conn: Conn,
                 user: Annotated[asyncpg.Record, Depends(require_role('admin'))]):
    """Set or clear HQ only; never touches alarm flags or radii, so no version check is needed.

    Clearing HQ ends its open alerts (as 'disabled', by this admin) in the same transaction: an HQ set again
    later then alarms afresh for a fire nearby, even one whose old alert was acknowledged."""
    resolved: list[str] = []
    async with conn.transaction():
        row = await repository.update_hq(conn, body.hq_latitude, body.hq_longitude, user['id'])
        if row is not None and body.hq_latitude is None:
            resolved = await fire_repository.resolve_hq_alerts(conn, user['id'])
    if row is None:
        raise _missing()
    await notify_alerts_updated(conn, resolved)
    out = _out(row)
    logger.info('HQ %s by user %s', 'cleared' if body.hq_latitude is None else 'set', user['id'])
    _changed()
    return out


@router.put('/hq-initial', response_model=SettingsOut)
async def put_hq_initial(body: HQIn, conn: Conn,
                         user: Annotated[asyncpg.Record, Depends(require_role('admin'))]):
    """One-time move of a browser's localStorage HQ into the database. Only while nobody has saved
    settings yet (updated_by IS NULL), so a cleared HQ is not resurrected by a legacy browser copy."""
    row = await repository.set_initial_hq(conn, body.hq_latitude, body.hq_longitude, user['id'])
    if row is None:
        if not await repository.row_exists(conn):
            raise _missing()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='hq_already_set')
    out = _out(row)
    logger.info('HQ %s by user %s', 'set (initial)', user['id'])
    _changed()
    return out
