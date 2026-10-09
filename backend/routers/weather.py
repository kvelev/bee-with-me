"""
OpenWeatherMap proxy — the API key stays on the server.

The browser used to call OWM directly with the key in every URL, so anyone using the map could
read it. These routes add the key server-side and are only open to logged-in users (the map loads
weather tiles through an authenticated tile loader, see composables/useMap.js).

    GET /api/weather/tiles/{layer}/{z}/{x}/{y}.png   map tile (clouds_new, precipitation_new, wind_new, temp_new)
    GET /api/weather/current?lat=&lon=               data/2.5/weather at one point (metric)
    GET /api/weather/box?bbox=&zoom=                 data/2.5/box/city (paid OWM plan only)

The key comes from OWM_API_KEY, or from the older VITE_OWM_API_KEY that existing .env files
carry. Without a key every route answers 503.
"""

import logging
import re
import time
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response

from ..auth import get_current_user
from ..config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/api/weather', tags=['weather'])

TILE_URL = 'https://tile.openweathermap.org/map/{layer}/{z}/{x}/{y}.png'
API_URL = 'https://api.openweathermap.org/data/2.5/{endpoint}'
LAYERS = frozenset({'clouds_new', 'precipitation_new', 'wind_new', 'temp_new'})
TIMEOUT = httpx.Timeout(10.0)

# Weather tiles change every ~10 min upstream; a small in-process cache keeps panning around
# the same area from spending the OWM quota again.
TILE_TTL_S = 600
TILE_CACHE_MAX = 512
_tile_cache: dict[tuple, tuple[float, bytes]] = {}

LoggedIn = Depends(get_current_user)


class _RedactAppid(logging.Filter):
    """httpx logs every request URL at INFO, and OWM only takes the key as `appid=` in the URL.
    Mask it so the key never lands in the backend log (or whatever collects it)."""
    _pattern = re.compile(r'(appid=)[^&\s"\']+')

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        if 'appid=' in message:
            record.msg, record.args = self._pattern.sub(r'\1***', message), ()
        return True


logging.getLogger('httpx').addFilter(_RedactAppid())


def _key() -> str:
    if not settings.owm_api_key:
        raise HTTPException(status_code=503, detail='Weather is not configured (OWM_API_KEY is not set)')
    return settings.owm_api_key


async def _get(url: str, params: dict) -> httpx.Response:
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            return await client.get(url, params=params)
    except httpx.HTTPError as exc:
        logger.warning('OpenWeatherMap unreachable: %s', type(exc).__name__)
        raise HTTPException(status_code=502, detail='OpenWeatherMap is unreachable')


@router.get('/tiles/{layer}/{z}/{x}/{y}.png', dependencies=[LoggedIn])
async def tile(
    layer: str,
    z: Annotated[int, Path(ge=0, le=19)],
    x: Annotated[int, Path(ge=0)],
    y: Annotated[int, Path(ge=0)],
):
    if layer not in LAYERS:
        raise HTTPException(status_code=404, detail='Unknown weather layer')
    if x >= 2 ** z or y >= 2 ** z:
        raise HTTPException(status_code=404, detail='Tile out of range')
    key = (layer, z, x, y)
    now = time.monotonic()
    cached = _tile_cache.get(key)
    if cached and now - cached[0] < TILE_TTL_S:
        content = cached[1]
    else:
        r = await _get(TILE_URL.format(layer=layer, z=z, x=x, y=y), {'appid': _key()})
        if r.status_code != 200:
            raise HTTPException(status_code=502, detail=f'OpenWeatherMap answered {r.status_code}')
        content = r.content
        if len(_tile_cache) >= TILE_CACHE_MAX:
            _tile_cache.pop(next(iter(_tile_cache)))   # oldest insertion first
        _tile_cache[key] = (now, content)
    return Response(content, media_type='image/png', headers={'Cache-Control': f'private, max-age={TILE_TTL_S}'})


@router.get('/current', dependencies=[LoggedIn])
async def current(
    lat: Annotated[float, Query(ge=-90, le=90)],
    lon: Annotated[float, Query(ge=-180, le=180)],
):
    r = await _get(API_URL.format(endpoint='weather'),
                   {'lat': round(lat, 4), 'lon': round(lon, 4), 'units': 'metric', 'appid': _key()})
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f'OpenWeatherMap answered {r.status_code}')
    return r.json()


@router.get('/box', dependencies=[LoggedIn])
async def box(
    bbox: Annotated[str, Query(pattern=r'^-?\d{1,3}(\.\d{1,2})?(,-?\d{1,3}(\.\d{1,2})?){3}$')],
    zoom: Annotated[int, Query(ge=3, le=14)],
):
    """box/city needs a paid OWM plan. A plan refusal is `{"denied": true}` (200), not an error status:
    the browser then stops asking for the session, and a 401 here would look like an expired login."""
    r = await _get(API_URL.format(endpoint='box/city'),
                   {'bbox': f'{bbox},{zoom}', 'units': 'metric', 'cnt': 50, 'appid': _key()})
    if r.status_code in (401, 403):
        return {'denied': True}
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f'OpenWeatherMap answered {r.status_code}')
    return r.json()
