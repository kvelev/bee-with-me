"""Characterisation of the Excel volunteer import (POST /api/users/import)."""
import io
from unittest.mock import AsyncMock

import pytest
from openpyxl import Workbook

from backend.routers.users import _find_col, _split_name

pytestmark = pytest.mark.Trait("Task", "T113")

XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


def _xlsx(rows: list[list]) -> bytes:
    wb = Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _post(client, rows, filename='volunteers.xlsx'):
    return client.post('/api/users/import', files={'file': (filename, _xlsx(rows), XLSX)})


def test_import_rejects_other_extensions(client, mock_conn):
    resp = client.post('/api/users/import', files={'file': ('volunteers.csv', b'name\nA', 'text/csv')})
    assert resp.status_code == 400
    assert resp.json()['detail'] == 'Only .xls and .xlsx files are accepted'
    mock_conn.execute.assert_not_awaited()


def test_import_without_name_column_is_400(client, mock_conn):
    resp = _post(client, [['Telephone', 'Rank'], ['0888', 'Sgt']])
    assert resp.status_code == 400
    assert resp.json()['detail'].startswith('Could not find a name column')
    mock_conn.execute.assert_not_awaited()


def test_import_creates_rows_and_normalises_pin(client, mock_conn):
    resp = _post(client, [['Доброволец', 'ПИН', 'Телефон'], ['Иван Петров', '1234.0', '0888']])
    assert resp.status_code == 200
    assert resp.json() == {'created': 1, 'skipped': []}
    mock_conn.execute.assert_awaited_once()
    assert 'INSERT INTO users' in mock_conn.execute.call_args.args[0]
    assert mock_conn.execute.call_args.args[1:] == ('Иван', 'Петров', 'Иван Петров', '0888', '1234')


def test_import_skips_empty_names_and_existing_people_with_row_numbers(client, mock_conn):
    mock_conn.fetchval = AsyncMock(side_effect=[None, 1])
    resp = _post(client, [
        ['Name', 'Phone'],
        ['Ana Ivanova', '1'],
        ['Boris Petrov', '2'],
        [None, '3'],
    ])
    assert resp.status_code == 200
    assert resp.json() == {
        'created': 1,
        'skipped': [
            {'row': 3, 'reason': 'already exists: "Boris Petrov"'},
            {'row': 4, 'reason': 'empty name'},
        ],
    }
    mock_conn.execute.assert_awaited_once()
    assert mock_conn.execute.call_args.args[3] == 'Ana Ivanova'


def test_split_name_and_find_col():
    assert _split_name('Иван Петров Георгиев') == ('Иван', 'Петров Георгиев')
    assert _split_name('Madonna') == ('Madonna', '')
    assert _split_name('   ') == ('', '')
    assert _find_col(['Name ', 'Tel'], 'phone', 'tel') == 'Tel'
    assert _find_col(['Rank'], 'name') is None
