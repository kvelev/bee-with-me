"""Characterisation of routers/export.py CSV and GeoJSON (PDF is covered by test_export_pdf.py)."""

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from backend.auth import get_current_user

pytestmark = [pytest.mark.Trait("Task", "T115")]

ROW = {'full_name': 'A', 'rank': None, 'dev_sn': 1, 'device_name': None, 'mgrs': '35T', 'latitude': 42.5,
       'longitude': 24.5, 'altitude_m': 1000.0, 'speed_knots': 0.0, 'gnss_satellites': 8, 'battery_voltage': 3.9,
       'sos_active': False, 'recorded_at': datetime(2026, 10, 1, tzinfo=timezone.utc), 'groups': 'Alpha'}

HEADER = ('full_name,rank,dev_sn,device_name,mgrs,latitude,longitude,altitude_m,speed_knots,'
          'gnss_satellites,battery_voltage,sos_active,recorded_at,groups')


def test_csv_has_header_in_query_order_and_attachment_name(client, mock_conn):
    mock_conn.fetch = AsyncMock(return_value=[ROW])
    resp = client.get('/api/export/csv')
    assert resp.status_code == 200
    assert resp.headers['content-type'].startswith('text/csv')
    assert resp.headers['content-disposition'] == 'attachment; filename="locations.csv"'
    lines = resp.text.splitlines()
    assert lines[0] == HEADER
    assert len(lines) == 2
    assert lines[1].startswith('A,,1,,35T,42.5,24.5,1000.0,')


def test_csv_with_no_rows_is_200(client, mock_conn):
    mock_conn.fetch = AsyncMock(return_value=[])
    resp = client.get('/api/export/csv')
    assert resp.status_code == 200
    assert resp.headers['content-disposition'] == 'attachment; filename="locations.csv"'
    assert resp.text.strip() == ''


def test_filters_are_passed_positionally(client, mock_conn):
    gid, uid = uuid.uuid4(), uuid.uuid4()
    mock_conn.fetch = AsyncMock(return_value=[])
    resp = client.get('/api/export/csv', params={
        'from': '2026-10-01T00:00:00+00:00', 'to': '2026-10-02T00:00:00+00:00',
        'group_id': str(gid), 'user_id': str(uid)})
    assert resp.status_code == 200
    assert mock_conn.fetch.call_args.args[1:] == (
        datetime(2026, 10, 1, tzinfo=timezone.utc), datetime(2026, 10, 2, tzinfo=timezone.utc), gid, uid)
    client.get('/api/export/csv')
    assert mock_conn.fetch.call_args.args[1:] == (None, None, None, None)


def test_geojson_points_are_lon_lat_and_skip_rows_without_latitude(client, mock_conn):
    no_fix = {**ROW, 'latitude': None, 'longitude': None, 'full_name': 'B'}
    mock_conn.fetch = AsyncMock(return_value=[ROW, no_fix])
    resp = client.get('/api/export/geojson')
    assert resp.status_code == 200
    assert resp.headers['content-type'].startswith('application/geo+json')
    body = json.loads(resp.text)
    assert body['type'] == 'FeatureCollection'
    assert len(body['features']) == 1
    feature = body['features'][0]
    assert feature['geometry'] == {'type': 'Point', 'coordinates': [24.5, 42.5]}
    assert 'latitude' not in feature['properties'] and 'longitude' not in feature['properties']
    assert feature['properties']['full_name'] == 'A'
    assert feature['properties']['recorded_at'] == str(ROW['recorded_at'])


@pytest.mark.parametrize('path', ['/api/export/csv', '/api/export/geojson'])
def test_exports_allowed_for_viewer(client, mock_conn, viewer_user, test_app, path):
    test_app.dependency_overrides[get_current_user] = lambda: viewer_user
    mock_conn.fetch = AsyncMock(return_value=[ROW])
    assert client.get(path).status_code == 200
