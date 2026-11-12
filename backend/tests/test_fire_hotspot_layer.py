"""B106: EFFIS/GWIS renamed the hotspot layer; the old name now answers 502 'TYPENAME doesn't exist'.

The fixtures are real responses recorded on 2026-11-11 (public service, our fixed request, see
backend/tests/fixtures/gwis/): the 502 for the old name, the GetCapabilities type names and the
GeoJSON of the new name.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from backend.modules.fire.domain.parse import parse_hotspots
from backend.modules.fire.infrastructure import sources as s

pytestmark = [pytest.mark.Trait("Task", "B106"), pytest.mark.asyncio]

FIX = Path(__file__).parent / 'fixtures' / 'gwis'
CAPABILITIES = set((FIX / 'capabilities_typenames.2026-11-11.txt').read_text().split())
UNKNOWN_TYPENAME = (FIX / 'unknown_typename.2026-11-11.xml').read_bytes()
WEEK_POINTS = (FIX / 'viirs.hs.week.points.2026-11-11.json').read_bytes()
NOW = datetime(2026, 11, 11, 18, 46, tzinfo=timezone.utc)


def _gwis_as_recorded(request):
    """Answers the way the real server did on 2026-11-11."""
    typename = request.url.params['TYPENAMES']
    if typename == 'ms:viirs.hs.week.points':
        return httpx.Response(200, content=WEEK_POINTS)
    if typename in CAPABILITIES:
        return httpx.Response(200, json={'type': 'FeatureCollection', 'features': []})
    return httpx.Response(502, content=UNKNOWN_TYPENAME, headers={'content-type': 'text/xml'})


async def test_configured_layers_are_advertised_by_the_service():
    assert s.HOTSPOTS.type_name in CAPABILITIES
    assert s.BURNT_AREAS.type_name in CAPABILITIES


async def test_hotspots_feed_yields_rows_from_the_recorded_service():
    feed = s.GwisFeed(s.HOTSPOTS.name, s.HOTSPOTS.type_name, transport=httpx.MockTransport(_gwis_as_recorded))
    rows = parse_hotspots(await feed.fetch(), now=NOW)
    assert len(rows) == len(json.loads(WEEK_POINTS)['features']) == 55


async def test_the_old_layer_name_is_refused_with_the_status():
    feed = s.GwisFeed('hotspots', 'ms:viirs.hs.week', transport=httpx.MockTransport(_gwis_as_recorded))
    with pytest.raises(s.FeedFetchError, match='502'):
        await feed.fetch()
