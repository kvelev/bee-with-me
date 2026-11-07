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
