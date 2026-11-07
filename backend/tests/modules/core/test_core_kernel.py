"""T300: backend/core/ is the shared kernel; backend.config stays importable as an alias of core.config."""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[4]


@pytest.mark.Trait("Task", "T300")
def test_kernel_package_is_core_not_platform():
    assert importlib.util.find_spec('backend.core') is not None
    assert not (REPO / 'backend' / 'platform').exists()
    # a package named `platform` inside backend/ would shadow the stdlib module for scripts run from there
    out = subprocess.run(
        [sys.executable, '-c', 'import platform; print(platform.__file__)'],
        cwd=REPO / 'backend', capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert (REPO / 'backend') not in Path(out).resolve().parents


@pytest.mark.Trait("Task", "T300")
def test_config_old_path_is_the_new_module():
    import backend.config as old
    import backend.core.config as new
    assert old is new
    assert old.settings is new.settings


@pytest.mark.Trait("Task", "T300")
def test_backup_marker_default_is_under_the_repo_root(monkeypatch):
    from backend.core.config import Settings
    monkeypatch.delenv('BACKUP_MARKER_PATH', raising=False)
    assert Settings(_env_file=None).backup_marker_path == REPO / 'data' / 'backups' / 'last-backup.json'


@pytest.mark.Trait("Task", "T300")
def test_relative_marker_path_resolves_against_the_repo_root():
    from backend.core.config import Settings
    assert Settings(_env_file=None, backup_marker_path=Path('x/y.json')).backup_marker_path == REPO / 'x' / 'y.json'


@pytest.mark.Trait("Task", "T302")
def test_ws_old_path_is_the_new_module():
    import backend.ws as old
    import backend.core.ws as new
    assert old is new
    assert old.manager is new.manager


@pytest.mark.Trait("Task", "T302")
def test_forwarded_channels_are_unchanged():
    from backend.core.ws import FORWARDED_CHANNELS
    assert FORWARDED_CHANNELS == (
        'location_update', 'sos_alert', 'fire_data_updated', 'fire_alert',
        'fire_alert_repeat', 'fire_alert_updated', 'fire_zones_updated',
    )


@pytest.mark.Trait("Task", "T302")
def test_core_ws_has_no_auth_or_origin_hook():
    # the move changes no behaviour: WebSocket authentication/origin checks are not implemented in this step
    src = (REPO / 'backend' / 'core' / 'ws.py').read_text(encoding='utf-8')
    assert 'Origin' not in src and 'jwt' not in src.lower()
    assert 'backend.core.ws' == __import__('backend.core.ws', fromlist=['x']).logger.name


@pytest.mark.Trait("Task", "T301")
def test_database_old_path_is_the_new_module():
    import backend.database as old
    import backend.core.database as new
    assert old is new
    assert old.get_conn is new.get_conn


@pytest.mark.Trait("Task", "T301")
def test_json_columns_old_path_is_the_new_module():
    import backend.json_columns as old
    import backend.core.json_columns as new
    assert old is new
    assert old.decode_json_columns is new.decode_json_columns


@pytest.mark.Trait("Task", "T301")
def test_pool_state_is_shared_through_the_old_path(monkeypatch):
    import backend.database as old
    import backend.core.database as new
    sentinel = object()
    monkeypatch.setattr(new, '_pool', sentinel)
    assert old.get_pool() is sentinel
    # patching by the old name reaches the live module too (tests that mock backend.database.* by name)
    other = object()
    monkeypatch.setattr(old, '_pool', other)
    assert new.get_pool() is other


@pytest.mark.Trait("Task", "T301")
def test_json_columns_logger_is_renamed(caplog):
    import logging
    from backend.json_columns import decode_json_columns
    with caplog.at_level(logging.WARNING):
        decode_json_columns({'g': 'not json'}, 'g')
    assert [r.name for r in caplog.records] == ['backend.core.json_columns']
