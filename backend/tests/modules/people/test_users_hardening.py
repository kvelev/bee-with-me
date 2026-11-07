"""Hardening of the people router: photo extension (B68), upload size cap (B75), no exception text to the client (B76)."""
import uuid

import pytest

PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 16


@pytest.fixture(autouse=True)
def upload_dir(monkeypatch, tmp_path):
    """No test in this module may write into the real backend/uploads (volunteer photos)."""
    target = tmp_path / 'uploads'
    target.mkdir()
    monkeypatch.setattr('backend.routers.users.UPLOAD_DIR', str(target))
    return target


# ── B68: extension comes from the content type, never from the client filename ──

@pytest.mark.Trait("Bug", "B68")
@pytest.mark.parametrize('filename,content_type,ext', [
    ('a.png/../../x', 'image/png', 'png'),      # path separators in the "extension"
    ('noextension', 'image/jpeg', 'jpg'),       # no dot: the whole name used to become the extension
    ('evil.php', 'image/webp', 'webp'),         # the filename extension is ignored
    (r'..\..\evil.exe', 'image/png', 'png'),   # Windows separators
])
def test_photo_extension_comes_from_content_type(client, mock_conn, upload_dir, tmp_path, filename, content_type, ext):
    uid = uuid.uuid4()

    resp = client.post(f'/api/users/{uid}/photo', files={'file': (filename, PNG, content_type)})

    assert resp.status_code == 200
    photo_url = resp.json()['photo_url']
    name = photo_url.removeprefix('/uploads/')
    assert name.endswith(f'.{ext}') and name.count('.') == 1 and '/' not in name and '\\' not in name
    uuid.UUID(name.rsplit('.', 1)[0])
    assert [p.name for p in upload_dir.iterdir()] == [name]
    assert {p.name for p in tmp_path.iterdir()} == {'uploads'}   # nothing written outside UPLOAD_DIR


@pytest.mark.Trait("Bug", "B68")
def test_photo_with_unmapped_content_type_is_rejected_without_write(client, mock_conn, upload_dir):
    resp = client.post(f'/api/users/{uuid.uuid4()}/photo', files={'file': ('a.png', PNG, 'image/gif')})

    assert resp.status_code == 400
    assert list(upload_dir.iterdir()) == []
    mock_conn.execute.assert_not_awaited()


# ── B75: uploads are capped, 413 before any parsing or writing ──

XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


def _xlsx_bytes() -> bytes:
    import io
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append(['Доброволец', 'ПИН'])
    ws.append(['Иван Петров', '1234'])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.mark.Trait("Bug", "B75")
def test_upload_limits_are_the_documented_ones():
    from backend.routers import users
    assert users.MAX_PHOTO_BYTES == 5 * 1024 * 1024
    assert users.MAX_IMPORT_BYTES == 10 * 1024 * 1024


@pytest.mark.Trait("Bug", "B75")
def test_photo_one_byte_over_the_limit_is_413_and_nothing_is_written(client, mock_conn, upload_dir, monkeypatch):
    monkeypatch.setattr('backend.routers.users.MAX_PHOTO_BYTES', len(PNG) - 1)

    resp = client.post(f'/api/users/{uuid.uuid4()}/photo', files={'file': ('a.png', PNG, 'image/png')})

    assert resp.status_code == 413
    assert list(upload_dir.iterdir()) == []
    mock_conn.execute.assert_not_awaited()


@pytest.mark.Trait("Bug", "B75")
def test_photo_at_the_limit_is_stored(client, mock_conn, upload_dir, monkeypatch):
    monkeypatch.setattr('backend.routers.users.MAX_PHOTO_BYTES', len(PNG))

    resp = client.post(f'/api/users/{uuid.uuid4()}/photo', files={'file': ('a.png', PNG, 'image/png')})

    assert resp.status_code == 200
    assert len(list(upload_dir.iterdir())) == 1


@pytest.mark.Trait("Bug", "B75")
def test_photo_cap_holds_when_the_size_is_unknown(client, mock_conn, upload_dir, monkeypatch):
    """The chunked read enforces the cap even when UploadFile.size is not available."""
    from starlette.datastructures import UploadFile
    monkeypatch.setattr(UploadFile, 'size', property(lambda self: None, lambda self, v: None), raising=False)
    monkeypatch.setattr('backend.routers.users.MAX_PHOTO_BYTES', len(PNG) - 1)

    resp = client.post(f'/api/users/{uuid.uuid4()}/photo', files={'file': ('a.png', PNG, 'image/png')})

    assert resp.status_code == 413
    assert list(upload_dir.iterdir()) == []


@pytest.mark.Trait("Bug", "B75")
def test_import_one_byte_over_the_limit_is_413_and_makes_no_db_call(client, mock_conn, monkeypatch):
    raw = _xlsx_bytes()
    monkeypatch.setattr('backend.routers.users.MAX_IMPORT_BYTES', len(raw) - 1)

    resp = client.post('/api/users/import', files={'file': ('v.xlsx', raw, XLSX)})

    assert resp.status_code == 413
    mock_conn.fetchval.assert_not_awaited()
    mock_conn.execute.assert_not_awaited()


@pytest.mark.Trait("Bug", "B75")
def test_import_at_the_limit_still_works(client, mock_conn, monkeypatch):
    raw = _xlsx_bytes()
    monkeypatch.setattr('backend.routers.users.MAX_IMPORT_BYTES', len(raw))

    resp = client.post('/api/users/import', files={'file': ('v.xlsx', raw, XLSX)})

    assert resp.status_code == 200
    assert resp.json()['created'] == 1
