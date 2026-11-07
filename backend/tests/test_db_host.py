"""B67: the database is reached over IPv4 loopback, never through `localhost`.

`localhost` resolves to ::1 first. The compose file publishes the DB port on 127.0.0.1 only, and on
Windows a refused ::1 connect takes about 2 s before the client falls back to IPv4, so every new
connection (pool min_size 2, migrate status, the LISTEN connection) paid 2 s at start.
"""

import re
from pathlib import Path

import pytest

from backend.config import Settings

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.Trait("Bug", "B67")
def test_default_host_is_ipv4_loopback():
    assert Settings(_env_file=None).postgres_host == '127.0.0.1'


@pytest.mark.Trait("Bug", "B67")
@pytest.mark.parametrize('value', ['localhost', 'LOCALHOST', ' localhost '])
def test_localhost_from_env_becomes_ipv4_loopback(value):
    assert Settings(_env_file=None, postgres_host=value).postgres_host == '127.0.0.1'


@pytest.mark.Trait("Bug", "B67")
@pytest.mark.parametrize('value', ['127.0.0.1', 'postgres', 'db.internal', '10.0.0.5', '::1'])
def test_other_hosts_are_kept(value):
    assert Settings(_env_file=None, postgres_host=value).postgres_host == value


@pytest.mark.Trait("Bug", "B67")
def test_start_ps1_waits_for_postgres_on_ipv4():
    text = (ROOT / 'start.ps1').read_text(encoding='utf-8')
    probes = re.findall(r"Test-NetConnection\s+-ComputerName\s+'([^']+)'", text)
    assert probes and all(host == '127.0.0.1' for host in probes), probes
