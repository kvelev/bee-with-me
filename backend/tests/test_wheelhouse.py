"""B62: integrity check of the offline wheel folder (scripts/wheelhouse.py)."""

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'wheelhouse.py'


def _run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True, timeout=60)


@pytest.fixture()
def wheels(tmp_path):
    folder = tmp_path / 'wheels'
    folder.mkdir()
    (folder / 'fastapi-1.0-py3-none-any.whl').write_bytes(b'fastapi wheel')
    (folder / 'bcrypt-4.1-cp311-abi3-win_amd64.whl').write_bytes(b'bcrypt wheel')
    return folder


@pytest.mark.Trait("Bug", "B62")
def test_written_sums_verify(wheels):
    assert _run('write', wheels).returncode == 0
    sums = (wheels / 'SHA256SUMS').read_text(encoding='utf-8').splitlines()
    assert len(sums) == 2 and all(len(line.split('  ')[0]) == 64 for line in sums)
    assert _run('verify', wheels).returncode == 0


@pytest.mark.Trait("Bug", "B62")
def test_changed_wheel_fails(wheels):
    _run('write', wheels)
    (wheels / 'fastapi-1.0-py3-none-any.whl').write_bytes(b'planted')
    res = _run('verify', wheels)
    assert res.returncode == 1 and 'fastapi-1.0-py3-none-any.whl' in res.stderr


@pytest.mark.Trait("Bug", "B62")
def test_unlisted_wheel_fails(wheels):
    _run('write', wheels)
    (wheels / 'python_jose-99.0-py3-none-any.whl').write_bytes(b'planted')
    res = _run('verify', wheels)
    assert res.returncode == 1 and 'python_jose-99.0' in res.stderr


@pytest.mark.Trait("Bug", "B62")
def test_source_archive_fails(wheels):
    _run('write', wheels)
    (wheels / 'mgrs-1.4.tar.gz').write_bytes(b'sdist')
    assert _run('verify', wheels).returncode == 1


@pytest.mark.Trait("Bug", "B62")
def test_listed_wheel_missing_fails(wheels):
    _run('write', wheels)
    (wheels / 'bcrypt-4.1-cp311-abi3-win_amd64.whl').unlink()
    assert _run('verify', wheels).returncode == 1


@pytest.mark.Trait("Bug", "B62")
@pytest.mark.parametrize('name', ['../outside-1.0-py3-none-any.whl', 'sub/pkg-1.0-py3-none-any.whl', 'mgrs-1.4.tar.gz'])
def test_listed_name_that_is_not_a_plain_wheel_fails(wheels, name):
    _run('write', wheels)
    with (wheels / 'SHA256SUMS').open('a', encoding='utf-8') as fh:
        fh.write(f'{"0" * 64}  {name}\n')
    res = _run('verify', wheels)
    assert res.returncode == 1 and 'not a wheel file name' in res.stderr


@pytest.mark.Trait("Bug", "B62")
def test_missing_sums_file_fails(wheels):
    res = _run('verify', wheels)
    assert res.returncode == 1 and 'SHA256SUMS' in res.stderr
