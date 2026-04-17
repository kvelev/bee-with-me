"""
Export routes — CSV, GeoJSON, PDF.
All exports share the same filter parameters: from/to datetime, group_id, user_id.
"""

from __future__ import annotations

import io
import json
from datetime import datetime
from uuid import UUID

import asyncpg
import pandas as pd
from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response, StreamingResponse

from ..auth import get_current_user
from ..database import get_conn

router = APIRouter(prefix='/api/export', tags=['export'])

_EXPORT_QUERY = """
    SELECT
        u.full_name, u.rank,
        d.dev_sn, d.name AS device_name,
        le.mgrs, le.latitude, le.longitude,
        le.altitude_m, le.speed_knots, le.gnss_satellites,
        le.battery_voltage, le.sos_active, le.recorded_at,
        STRING_AGG(g.name, ', ') AS groups
    FROM location_events le
    JOIN devices d ON d.id = le.device_id
    LEFT JOIN users u ON u.id = le.user_id
    LEFT JOIN user_groups ug ON ug.user_id = le.user_id
    LEFT JOIN groups g ON g.id = ug.group_id
    WHERE ($1::timestamptz IS NULL OR le.recorded_at >= $1)
      AND ($2::timestamptz IS NULL OR le.recorded_at <= $2)
      AND ($3::uuid IS NULL OR ug.group_id = $3)
      AND ($4::uuid IS NULL OR le.user_id = $4)
    GROUP BY u.full_name, u.rank, d.dev_sn, d.name,
             le.mgrs, le.latitude, le.longitude, le.altitude_m,
             le.speed_knots, le.gnss_satellites, le.battery_voltage,
             le.sos_active, le.recorded_at
    ORDER BY le.recorded_at DESC
"""


async def _fetch_rows(
    conn: asyncpg.Connection,
    from_dt: datetime | None,
    to_dt: datetime | None,
    group_id: UUID | None,
    user_id: UUID | None,
) -> list[dict]:
    rows = await conn.fetch(_EXPORT_QUERY, from_dt, to_dt, group_id, user_id)
    return [dict(r) for r in rows]


@router.get('/csv')
async def export_csv(
    conn: asyncpg.Connection = Depends(get_conn),
    _=Depends(get_current_user),
    from_dt: datetime | None = Query(None, alias='from'),
    to_dt: datetime | None = Query(None, alias='to'),
    group_id: UUID | None = None,
    user_id: UUID | None = None,
):
    rows = await _fetch_rows(conn, from_dt, to_dt, group_id, user_id)
    df = pd.DataFrame(rows)
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return Response(
        content=buf.getvalue(),
        media_type='text/csv',
        headers={'Content-Disposition': 'attachment; filename="locations.csv"'},
    )


@router.get('/geojson')
async def export_geojson(
    conn: asyncpg.Connection = Depends(get_conn),
    _=Depends(get_current_user),
    from_dt: datetime | None = Query(None, alias='from'),
    to_dt: datetime | None = Query(None, alias='to'),
    group_id: UUID | None = None,
    user_id: UUID | None = None,
):
    rows = await _fetch_rows(conn, from_dt, to_dt, group_id, user_id)
    features = [
        {
            'type': 'Feature',
            'geometry': {'type': 'Point', 'coordinates': [r['longitude'], r['latitude']]},
            'properties': {k: v for k, v in r.items() if k not in ('latitude', 'longitude')},
        }
        for r in rows
        if r.get('latitude') is not None
    ]
    collection = json.dumps({'type': 'FeatureCollection', 'features': features}, default=str)
    return Response(
        content=collection,
        media_type='application/geo+json',
        headers={'Content-Disposition': 'attachment; filename="locations.geojson"'},
    )


@router.get('/pdf')
async def export_pdf(
    conn: asyncpg.Connection = Depends(get_conn),
    _=Depends(get_current_user),
    from_dt: datetime | None = Query(None, alias='from'),
    to_dt: datetime | None = Query(None, alias='to'),
    group_id: UUID | None = None,
    user_id: UUID | None = None,
):
    from weasyprint import HTML

    rows = await _fetch_rows(conn, from_dt, to_dt, group_id, user_id)

    period = f"{from_dt or 'all'} → {to_dt or 'now'}"
    rows_html = ''.join(
        f"""<tr>
            <td>{r.get('full_name','—')}</td>
            <td>{r.get('rank','—')}</td>
            <td>{r.get('groups','—')}</td>
            <td>{r['mgrs']}</td>
            <td>{r.get('altitude_m','—')}</td>
            <td>{r.get('speed_knots','—')}</td>
            <td>{r.get('battery_voltage','—')}</td>
            <td>{'YES' if r.get('sos_active') else ''}</td>
            <td>{r['recorded_at']}</td>
        </tr>"""
        for r in rows
    )

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  body {{ font-family: sans-serif; font-size: 9px; margin: 1cm; }}
  h1 {{ font-size: 14px; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ border: 1px solid #ccc; padding: 3px 5px; text-align: left; }}
  th {{ background: #2c3e50; color: white; }}
  tr:nth-child(even) {{ background: #f5f5f5; }}
  .sos {{ color: red; font-weight: bold; }}
</style>
</head><body>
<h1>Rescuer Locator — Location Report</h1>
<p>Period: {period} | Total records: {len(rows)}</p>
<table>
  <thead><tr>
    <th>Name</th><th>Rank</th><th>Groups</th><th>MGRS</th>
    <th>Alt (m)</th><th>Speed (kn)</th><th>Battery</th><th>SOS</th><th>Time (UTC)</th>
  </tr></thead>
  <tbody>{rows_html}</tbody>
</table>
</body></html>"""

    pdf = HTML(string=html).write_pdf()
    return Response(
        content=pdf,
        media_type='application/pdf',
        headers={'Content-Disposition': 'attachment; filename="locations.pdf"'},
    )
