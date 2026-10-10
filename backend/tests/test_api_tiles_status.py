"""GET /api/tiles/bgmountains/status reports whether this server has downloaded tiles (`available`),
which the browser uses to default BG Mountains to online or offline (composables/useSettings.js)."""

from backend.routers import tiles


def _app_with_tiles(client, monkeypatch, tmp_path):
    monkeypatch.setattr(tiles, 'TILE_DIR', str(tmp_path))
    return client


def test_status_without_downloaded_tiles(client, monkeypatch, tmp_path):
    c = _app_with_tiles(client, monkeypatch, tmp_path)
    r = c.get('/api/tiles/bgmountains/status')
    assert r.status_code == 200
    assert r.json()['available'] is False and r.json()['running'] is False


def test_status_with_a_downloaded_tile(client, monkeypatch, tmp_path):
    (tmp_path / '8' / '143').mkdir(parents=True)
    (tmp_path / '8' / '143' / '94.png').write_bytes(b'\x89PNG')
    c = _app_with_tiles(client, monkeypatch, tmp_path)
    assert c.get('/api/tiles/bgmountains/status').json()['available'] is True


def test_status_ignores_stray_files(client, monkeypatch, tmp_path):
    (tmp_path / 'README.txt').write_text('not a tile')
    (tmp_path / '8').mkdir()
    c = _app_with_tiles(client, monkeypatch, tmp_path)
    assert c.get('/api/tiles/bgmountains/status').json()['available'] is False
