"""
Fire feed sources: one adapter per upstream layer (Strategy), plus a fixture source for tests.

Everything about the request is fixed here — URL, layer, bbox, feature cap. Nothing a user sends is
ever forwarded upstream. The response body is capped, so a broken or hostile upstream can't exhaust
a field laptop's memory.
"""

from __future__ import annotations

import json
from typing import Protocol

import httpx

from ....version import APP_VERSION

GWIS_URL = 'https://maps.effis.emergency.copernicus.eu/gwis'
FEATURE_LIMIT = 5000   # WFS COUNT; a response this long is probably truncated
BASE_PARAMS = {
    'SERVICE': 'WFS',
    'VERSION': '2.0.0',
    'REQUEST': 'GetFeature',
    'OUTPUTFORMAT': 'GEOJSON',
    'COUNT': str(FEATURE_LIMIT),
    # WFS 2.0 + EPSG:4326 URN = lat,lon axis order. lon,lat silently returns Saudi Arabia.
    'BBOX': '41.2,22.3,44.3,28.7,urn:ogc:def:crs:EPSG::4326',
}
MAX_JSON_INT_DIGITS = 30   # Python's json raises ValueError on integer literals over 4300 digits: don't lose the feed for one
MAX_BODY_BYTES = 16 * 1024 * 1024
TIMEOUT_S = 90
USER_AGENT = f'BeeWithMe/{APP_VERSION}'


def _bounded_int(text: str):
    """Absurd integer literals become NaN, which the parsers reject as non-finite: only that feature is dropped."""
    return int(text) if len(text) <= MAX_JSON_INT_DIGITS else float('nan')


class FeedFetchError(RuntimeError):
    pass


class FireFeedSource(Protocol):
    name: str

    async def fetch(self) -> object: ...


class GwisFeed:
    def __init__(self, name: str, type_name: str, transport: httpx.AsyncBaseTransport | None = None):
        self.name = name
        self.type_name = type_name
        self._transport = transport

    async def fetch(self) -> object:
        params = {**BASE_PARAMS, 'TYPENAMES': self.type_name}
        cap = MAX_BODY_BYTES
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT_S, headers={'User-Agent': USER_AGENT, 'Accept-Encoding': 'identity'},
                                         follow_redirects=False, transport=self._transport) as client:
                async with client.stream('GET', GWIS_URL, params=params) as resp:
                    if resp.status_code != 200:
                        raise FeedFetchError(f'{self.name}: HTTP {resp.status_code}')
                    declared = resp.headers.get('content-length', '')
                    if declared.isdigit() and int(declared) > cap:
                        raise FeedFetchError(f'{self.name}: response too large ({declared} bytes)')
                    body, size = bytearray(), 0
                    async for chunk in resp.aiter_bytes():
                        size += len(chunk)
                        if size > cap:
                            raise FeedFetchError(f'{self.name}: response too large (>{cap} bytes)')
                        body.extend(chunk)
        except httpx.HTTPError as exc:
            raise FeedFetchError(f'{self.name}: {exc}') from exc
        try:
            return json.loads(bytes(body), parse_int=_bounded_int)
        except ValueError as exc:
            raise FeedFetchError(f'{self.name}: response is not JSON') from exc


class FixtureSource:
    """Test double: returns a fixed payload or raises a fixed error."""

    def __init__(self, name: str, payload=None, error: Exception | None = None):
        self.name = name
        self._payload = payload
        self._error = error

    async def fetch(self) -> object:
        if self._error is not None:
            raise self._error
        return self._payload


HOTSPOTS = GwisFeed('hotspots', 'ms:viirs.hs.week.points')   # renamed upstream (B106); GetCapabilities lists the names
BURNT_AREAS = GwisFeed('burnt_areas', 'ms:nrt.ba.poly.week')
