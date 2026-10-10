import logging
from datetime import datetime
from typing import Annotated, Callable

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, StrictBool, model_validator

from ..auth import get_current_user, require_role
from ..database import get_conn
from ..fire import repository as fire_repository
from ..fire.service import notify_alerts_updated

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/api/settings', tags=['settings'])

after_change: Callable[[], None] | None = None   # set by the alarm service (Task 16)

Conn = Annotated[asyncpg.Connection, Depends(get_conn)]

# Strict: JSON strings ("false", "5") and 0/1 for booleans are 422, never coerced (BP-02).
StrictLat = Annotated[float, Field(strict=True, ge=-90, le=90)]
StrictLon = Annotated[float, Field(strict=True, ge=-180, le=180)]
StrictInt = Annotated[int, Field(strict=True)]


class HQIn(BaseModel):
    hq_latitude: StrictLat
    hq_longitude: StrictLon


class HQPatch(BaseModel):
    """PUT /api/settings/hq: both numbers (set) or both null (clear)."""
    hq_latitude: StrictLat | None
    hq_longitude: StrictLon | None

    @model_validator(mode='after')
    def _hq_both_or_neither(self):
        if (self.hq_latitude is None) != (self.hq_longitude is None):
            raise ValueError('hq_latitude and hq_longitude must both be set or both be empty')
        return self


class SettingsIn(BaseModel):
    hq_latitude: StrictLat | None = None
    hq_longitude: StrictLon | None = None
    is_hq_alarm_enabled: StrictBool
    is_rescuer_alarm_enabled: StrictBool
    hq_radius_m: Annotated[StrictInt, Field(ge=100, le=100_000)]
    rescuer_radius_m: Annotated[StrictInt, Field(ge=100, le=100_000)]
    alarm_max_age_hours: Annotated[StrictInt, Field(ge=1, le=168)]
    repeat_minutes: Annotated[StrictInt, Field(ge=1, le=60)]
    is_rescuer_photo_on_map_enabled: StrictBool

    @model_validator(mode='after')
    def _hq_both_or_neither(self):
        if (self.hq_latitude is None) != (self.hq_longitude is None):
            raise ValueError('hq_latitude and hq_longitude must both be set or both be empty')
        return self


class SettingsUpdate(SettingsIn):
    expected_updated_at: datetime   # the updated_at the client last saw (optimistic concurrency)


class SettingsOut(SettingsIn):
    updated_at: datetime


def _out(row) -> SettingsOut:
    return SettingsOut(**{k: row[k] for k in SettingsOut.model_fields})


def _changed() -> None:
    if after_change is not None:
        after_change()


def _missing() -> HTTPException:
    logger.error('settings row (id=1) is missing; restore it from a backup or re-run the migrations')
    return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail='settings_missing')


async def _row_exists(conn) -> bool:
    return await conn.fetchval('SELECT 1 FROM settings WHERE id = 1') is not None


@router.get('', response_model=SettingsOut)
async def get_settings(conn: Conn, _: Annotated[asyncpg.Record, Depends(get_current_user)]):
    row = await conn.fetchrow('SELECT * FROM settings WHERE id = 1')
    if row is None:
        raise _missing()
    return _out(row)


@router.put('', response_model=SettingsOut)
async def put_settings(body: SettingsUpdate, conn: Conn,
                       user: Annotated[asyncpg.Record, Depends(require_role('admin'))]):
    resolved: list[str] = []
    async with conn.transaction():
        row = await conn.fetchrow(
            """UPDATE settings SET hq_latitude = $1, hq_longitude = $2, is_hq_alarm_enabled = $3,
                   is_rescuer_alarm_enabled = $4, hq_radius_m = $5, rescuer_radius_m = $6,
                   alarm_max_age_hours = $7, repeat_minutes = $8,
                   is_rescuer_photo_on_map_enabled = $9, updated_by = $10
               WHERE id = 1 AND updated_at = $11 RETURNING *""",
            body.hq_latitude, body.hq_longitude, body.is_hq_alarm_enabled, body.is_rescuer_alarm_enabled,
            body.hq_radius_m, body.rescuer_radius_m, body.alarm_max_age_hours, body.repeat_minutes,
            body.is_rescuer_photo_on_map_enabled, user['id'], body.expected_updated_at,
        )
        if row is not None and body.hq_latitude is None:
            resolved = await fire_repository.resolve_hq_alerts(conn, user['id'])
    if row is None:
        if not await _row_exists(conn):
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
        row = await conn.fetchrow(
            """UPDATE settings SET hq_latitude = $1, hq_longitude = $2, updated_by = $3
               WHERE id = 1 RETURNING *""",
            body.hq_latitude, body.hq_longitude, user['id'],
        )
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
    row = await conn.fetchrow(
        """UPDATE settings SET hq_latitude = $1, hq_longitude = $2, updated_by = $3
           WHERE id = 1 AND hq_latitude IS NULL AND updated_by IS NULL RETURNING *""",
        body.hq_latitude, body.hq_longitude, user['id'],
    )
    if row is None:
        if not await _row_exists(conn):
            raise _missing()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='hq_already_set')
    out = _out(row)
    logger.info('HQ %s by user %s', 'set (initial)', user['id'])
    _changed()
    return out
