import logging
from typing import Annotated, Literal
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import AwareDatetime, BaseModel, Field, field_validator, model_validator

from ...auth import get_current_user, require_role
from ...core.database import get_conn
from .infrastructure import poller, repository
from .domain.models import FireAlertOut, burnt_area_feature, hotspot_feature, iso, zone_out
from .domain.parse import is_storable
from .infrastructure.poller import notify_data_changed
from .infrastructure.service import notify
from .infrastructure.service import service as fire_alarm

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/api/fire', tags=['fire'])

Conn = Annotated[asyncpg.Connection, Depends(get_conn)]
User = Annotated[asyncpg.Record, Depends(get_current_user)]
Admin = Annotated[asyncpg.Record, Depends(require_role('admin'))]

FEED_TABLES = {'hotspots': 'fire_hotspots', 'burnt_areas': 'fire_burnt_areas'}


async def _fetched_at(conn, feed: str):
    """In-memory success time, else the newest row in the DB (the in-memory state is empty after a restart)."""
    return poller.FEEDS[feed].last_success_at or await repository.last_seen_at(conn, FEED_TABLES[feed])


@router.get('/hotspots')
async def hotspots(conn: Conn, _: User):
    rows = await repository.list_hotspots(conn)
    return {
        'type': 'FeatureCollection',
        'fetched_at': iso(await _fetched_at(conn, 'hotspots')),
        'upstream_state': poller.FEEDS['hotspots'].upstream_state,
        'features': [hotspot_feature(r) for r in rows],
    }


@router.get('/burnt-areas')
async def burnt_areas(conn: Conn, _: User):
    rows = await repository.list_burnt_areas(conn)
    return {
        'type': 'FeatureCollection',
        'fetched_at': iso(await _fetched_at(conn, 'burnt_areas')),
        'upstream_state': poller.FEEDS['burnt_areas'].upstream_state,
        'features': [burnt_area_feature(r) for r in rows],
    }


@router.get('/status')
async def status(conn: Conn, _: User):
    feeds = {}
    for name, state in poller.FEEDS.items():
        feeds[name] = {
            'last_success_at': iso(await _fetched_at(conn, name)),
            'last_error': state.last_error,
            'upstream_state': state.upstream_state,
            # null until this process has fetched the feed: after a restart 0 would contradict the DB
            'count': state.count if state.last_success_at is not None else None,
        }
    try:
        targets = await repository.count_targets(conn)
    except repository.SettingsMissingError:
        # feed health must still render; alarm targets are unknown without the settings row (BP-03)
        logger.error('fire status: settings row is missing, alarm targets unavailable')
        targets = None
    return {
        'feeds': feeds,
        'last_success_at': feeds['hotspots']['last_success_at'],
        'upstream_state': poller.FEEDS['hotspots'].upstream_state,
        'targets': targets,
    }


@router.get('/alerts', response_model=list[FireAlertOut])
async def list_alerts(response: Response, conn: Conn, _: User,
                      state: Literal['open', 'all'] = 'open',
                      limit: int = Query(50, ge=1, le=500),
                      offset: int = Query(0, ge=0)):
    rows = await repository.list_alerts(conn, state, limit, offset)
    # total rows for the filter, ignoring paging: the client shows "N more not shown" past its page
    response.headers['X-Total-Count'] = str(await repository.count_alerts(conn, state))
    return rows


class AcknowledgeAllBody(BaseModel):
    alert_ids: list[UUID] = Field(max_length=1000)


# Declared before /alerts/{alert_id}/acknowledge so the literal path wins.
@router.post('/alerts/acknowledge-all')
async def acknowledge_all(conn: Conn, user: User, body: AcknowledgeAllBody | None = None):
    """With a body only the listed alerts are acknowledged (the ones the operator can see); without one, all open."""
    async with conn.transaction():
        ids = await repository.acknowledge_all(conn, user['id'], body.alert_ids if body else None)
        for alert_id in ids:
            out = await repository.get_alert_out(conn, alert_id)
            if out is not None:
                await notify(conn, 'fire_alert_updated', out.model_dump(mode='json'))
    return {'acknowledged': len(ids)}


@router.post('/alerts/{alert_id}/acknowledge', response_model=FireAlertOut)
async def acknowledge(alert_id: UUID, conn: Conn, user: User):
    async with conn.transaction():
        out, changed = await repository.acknowledge_alert(conn, str(alert_id), user['id'])
        if out is None:
            raise HTTPException(status_code=404, detail='Alert not found')
        if changed:
            await notify(conn, 'fire_alert_updated', out.model_dump(mode='json'))
    return out


# -- operator writes (T18) ----------------------------------------------------------------------------------------

NOTES_MAX = 1000


def _text_ok(value: str | None, max_len: int) -> str | None:
    """Free text typed by an operator must be storable (no NUL, no lone surrogate): refuse it, never alter it."""
    if value is not None and not is_storable(value, max_len):
        raise ValueError('text contains characters that cannot be stored')
    return value


def _notes_validator():
    return field_validator('notes', mode='after')(classmethod(lambda cls, value: _text_ok(value, NOTES_MAX)))


def _label_validator():
    return field_validator('label', mode='after')(classmethod(lambda cls, value: _text_ok(value, 255)))


class DismissIn(BaseModel):
    notes: str | None = Field(default=None, max_length=NOTES_MAX)
    _notes_ok = _notes_validator()


class FieldReportIn(BaseModel):
    device_id: UUID | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    notes: str | None = Field(default=None, max_length=NOTES_MAX)
    _notes_ok = _notes_validator()

    @model_validator(mode='after')
    def _exactly_one_location(self):
        coords = (self.latitude, self.longitude)
        if self.device_id is not None:
            if any(c is not None for c in coords):
                raise ValueError('send device_id or coordinates, not both')
        elif None in coords:
            raise ValueError('send device_id, or both latitude and longitude')
        return self


class ZoneIn(BaseModel):
    label: str = Field(min_length=1, max_length=255)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    radius_m: int = Field(default=1000, ge=50, le=20_000)
    notes: str | None = Field(default=None, max_length=NOTES_MAX)
    _label_ok = _label_validator()
    _notes_ok = _notes_validator()


class ZoneUpdate(ZoneIn):
    """Edit body. `expected_updated_at` is the version the client read: a mismatch is a 409, never a silent overwrite.
    Activation is explicit (enable/disable), so `is_active` is refused rather than ignored."""
    expected_updated_at: AwareDatetime

    @model_validator(mode='before')
    @classmethod
    def _no_activation_in_an_edit(cls, data):
        if isinstance(data, dict) and 'is_active' in data:
            raise ValueError('is_active cannot be set by an edit: use the enable or disable endpoint')
        return data


class ZoneVersion(BaseModel):
    expected_updated_at: AwareDatetime


def _zone_data(body: ZoneIn) -> dict:
    return body.model_dump(include={'label', 'latitude', 'longitude', 'radius_m', 'notes'})


@router.post('/hotspots/{hotspot_id}/dismiss')
async def dismiss_hotspot(hotspot_id: UUID, body: DismissIn, conn: Conn, user: Admin):
    row = await repository.dismiss_hotspot(conn, str(hotspot_id), user['id'], body.notes)
    if row is None:
        raise HTTPException(status_code=404, detail='Hotspot not found')
    fire_alarm.request_evaluation()
    await notify_data_changed(conn)
    return hotspot_feature(row)


@router.post('/field-reports', status_code=201)
async def create_field_report(body: FieldReportIn, conn: Conn, user: User):
    latitude, longitude, device_id = body.latitude, body.longitude, None
    if body.device_id is not None:
        device_id = str(body.device_id)
        position = await repository.latest_device_position(conn, device_id)
        if position is None:
            raise HTTPException(status_code=409, detail='no_recent_position')
        latitude, longitude = position['latitude'], position['longitude']
    row = await repository.insert_field_report(conn, latitude, longitude, user['id'], device_id, body.notes)
    fire_alarm.request_evaluation()
    await notify_data_changed(conn)
    return hotspot_feature(row)


@router.post('/field-reports/{hotspot_id}/extinguish')
async def extinguish_field_report(hotspot_id: UUID, conn: Conn, user: User):
    row = await repository.extinguish_field_report(conn, str(hotspot_id), user['id'])
    if row is None:
        raise HTTPException(status_code=404, detail='Field report not found')
    fire_alarm.request_evaluation()
    await notify_data_changed(conn)
    return hotspot_feature(row)


@router.get('/suppression-zones')
async def list_zones(conn: Conn, _: User, include_disabled: bool = False):
    return [zone_out(r) for r in await repository.list_zones(conn, include_disabled)]


async def _zone_changed(conn, action: str, zone_id, user, is_active: bool) -> None:
    """Every zone write: one audit line (ids and state only, no label or notes), re-evaluate the alarm, tell the
    other browsers to refetch zones. Best effort for the broadcast: the write is already committed."""
    logger.info('fire zone %s: actor=%s zone=%s is_active=%s', action, user['id'], zone_id, is_active)
    fire_alarm.request_evaluation()
    try:
        await notify(conn, 'fire_zones_updated', {})
    except Exception as exc:  # noqa: BLE001
        logger.warning('fire zone broadcast failed: %s', exc)


async def _guarded_zone_write(write, zone_id: UUID):
    """Map the repository outcome to the contract: None = 404 zone not found, ZoneStaleError = 409 zone_stale."""
    try:
        row = await write
    except repository.ZoneStaleError:
        raise HTTPException(status_code=409, detail='zone_stale')
    if row is None:
        raise HTTPException(status_code=404, detail='Zone not found')
    return row


@router.post('/suppression-zones', status_code=201)
async def create_zone(body: ZoneIn, conn: Conn, user: Admin):
    row = await repository.create_zone(conn, _zone_data(body), user['id'])
    await _zone_changed(conn, 'created', row['id'], user, row['is_active'])
    return zone_out(row)


@router.put('/suppression-zones/{zone_id}')
async def update_zone(zone_id: UUID, body: ZoneUpdate, conn: Conn, user: Admin):
    row = await _guarded_zone_write(
        repository.update_zone(conn, str(zone_id), _zone_data(body), body.expected_updated_at, user['id']), zone_id)
    await _zone_changed(conn, 'updated', zone_id, user, row['is_active'])
    return zone_out(row)


@router.post('/suppression-zones/{zone_id}/disable')
async def disable_zone_versioned(zone_id: UUID, body: ZoneVersion, conn: Conn, user: Admin):
    row = await _guarded_zone_write(
        repository.set_zone_active(conn, str(zone_id), False, body.expected_updated_at, user['id']), zone_id)
    await _zone_changed(conn, 'disabled', zone_id, user, False)
    return zone_out(row)


@router.post('/suppression-zones/{zone_id}/enable')
async def enable_zone(zone_id: UUID, body: ZoneVersion, conn: Conn, user: Admin):
    row = await _guarded_zone_write(
        repository.set_zone_active(conn, str(zone_id), True, body.expected_updated_at, user['id']), zone_id)
    await _zone_changed(conn, 'enabled', zone_id, user, True)
    return zone_out(row)


@router.delete('/suppression-zones/{zone_id}')
async def disable_zone(zone_id: UUID, conn: Conn, user: Admin):
    """Alias of disable without the concurrency token (compatibility); the daily cleanup removes it 48 h later."""
    row = await repository.disable_zone(conn, str(zone_id), user['id'])
    if row is None:
        raise HTTPException(status_code=404, detail='Zone not found')
    await _zone_changed(conn, 'disabled', zone_id, user, False)
    return zone_out(row)
