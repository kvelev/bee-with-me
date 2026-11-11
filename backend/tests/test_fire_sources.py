"""GwisFeed: fixed request, bounded response, every failure as FeedFetchError."""

import httpx
import pytest

from backend.fire import sources as s
from backend.version import APP_VERSION

pytestmark = [pytest.mark.Trait("Task", "T8"), pytest.mark.asyncio]

EMPTY = {'type': 'FeatureCollection', 'features': []}


def _feed(handler):
    return s.GwisFeed('hotspots', 'ms:viirs.hs.week', transport=httpx.MockTransport(handler))


async def test_request_is_fixed_and_identifies_the_app():
    seen = {}

    def handler(request):
        seen['url'] = request.url
        seen['ua'] = request.headers['user-agent']
        return httpx.Response(200, json=EMPTY)

    assert await _feed(handler).fetch() == EMPTY
    url = seen['url']
    assert (url.scheme, url.host, url.path) == ('https', 'maps.effis.emergency.copernicus.eu', '/gwis')
    q = dict(url.params)
    assert q == {**s.BASE_PARAMS, 'TYPENAMES': 'ms:viirs.hs.week'}
    assert q['BBOX'] == '41.2,22.3,44.3,28.7,urn:ogc:def:crs:EPSG::4326'
    assert q['COUNT'] == '5000' and q['OUTPUTFORMAT'] == 'GEOJSON'
    assert seen['ua'] == f'BeeWithMe/{APP_VERSION}'


async def test_module_feeds_use_the_agreed_layers():
    assert s.HOTSPOTS.type_name == 'ms:viirs.hs.week.points'
    assert s.BURNT_AREAS.type_name == 'ms:nrt.ba.poly.week'


@pytest.mark.parametrize('status', [404, 500, 502, 503])
async def test_http_errors_raise(status):
    with pytest.raises(s.FeedFetchError, match=str(status)):
        await _feed(lambda r: httpx.Response(status, text='down')).fetch()


async def test_declared_oversize_body_is_refused(monkeypatch):
    monkeypatch.setattr(s, 'MAX_BODY_BYTES', 10)
    with pytest.raises(s.FeedFetchError, match='too large'):
        await _feed(lambda r: httpx.Response(200, json=EMPTY)).fetch()


async def test_streamed_oversize_body_is_refused(monkeypatch):
    monkeypatch.setattr(s, 'MAX_BODY_BYTES', 10)

    async def chunks():
        yield b'{"type": '
        yield b'"FeatureCollection"}'

    with pytest.raises(s.FeedFetchError, match='too large'):
        await _feed(lambda r: httpx.Response(200, content=chunks())).fetch()


async def test_non_json_body_raises():
    with pytest.raises(s.FeedFetchError, match='JSON'):
        await _feed(lambda r: httpx.Response(200, text='<html>maintenance</html>')).fetch()


async def test_network_errors_and_timeouts_raise():
    def handler(request):
        raise httpx.ReadTimeout('timed out', request=request)

    with pytest.raises(s.FeedFetchError, match='timed out'):
        await _feed(handler).fetch()


async def test_fixture_source():
    assert await s.FixtureSource('x', payload=EMPTY).fetch() == EMPTY
    with pytest.raises(s.FeedFetchError):
        await s.FixtureSource('x', error=s.FeedFetchError('boom')).fetch()


@pytest.mark.Trait("Bug", "B25")
async def test_redirects_are_refused_without_a_second_request():
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(302, headers={'location': 'https://evil.example/gwis'})

    with pytest.raises(s.FeedFetchError, match='302'):
        await _feed(handler).fetch()
    assert len(calls) == 1 and 'evil.example' not in calls[0]


@pytest.mark.Trait("Bug", "B25")
async def test_client_is_built_with_follow_redirects_explicitly_off(monkeypatch):
    seen = {}
    real = httpx.AsyncClient

    def spy(*args, **kwargs):
        seen.update(kwargs)
        return real(*args, **kwargs)

    monkeypatch.setattr(s.httpx, 'AsyncClient', spy)
    await _feed(lambda r: httpx.Response(200, json=EMPTY)).fetch()
    assert seen.get('follow_redirects') is False


@pytest.mark.Trait("Bug", "B30")
async def test_request_asks_for_an_uncompressed_body():
    seen = {}

    def handler(request):
        seen['accept_encoding'] = request.headers['accept-encoding']
        return httpx.Response(200, json=EMPTY)

    await _feed(handler).fetch()
    assert seen['accept_encoding'] == 'identity'


@pytest.mark.Trait("Bug", "B31")
async def test_absurd_integer_literal_drops_only_that_feature():
    from backend.fire import parse as p
    huge = '9' * 4400
    body = ('{"type":"FeatureCollection","features":['
            '{"type":"Feature","properties":{"id":%s,"acq_at":"2026-10-02 10:00:00"},'
            '"geometry":{"type":"Point","coordinates":[24.5,42.5]}},'
            '{"type":"Feature","properties":{"id":"good","acq_at":"2026-10-02 10:00:00"},'
            '"geometry":{"type":"Point","coordinates":[24.5,42.5]}}]}' % huge).encode()
    payload = await _feed(lambda request: httpx.Response(200, content=body)).fetch()
    stats = p.ParseStats()
    rows = p.parse_hotspots(payload, now=p.datetime(2026, 10, 2, 12, 0, tzinfo=p.timezone.utc), stats=stats)
    assert [r.effis_id for r in rows] == ['good']
    assert stats.malformed == 1


@pytest.mark.Trait("Bug", "B31")
async def test_reasonable_integers_stay_integers():
    payload = await _feed(lambda request: httpx.Response(200, content=b'{"a": 65324783454}')).fetch()
    assert payload == {'a': 65324783454} and isinstance(payload['a'], int)
