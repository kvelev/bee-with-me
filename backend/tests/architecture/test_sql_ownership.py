"""Writes into a table must come from the module that owns it; today's violations are allowlisted and may only shrink."""
import json
from pathlib import Path

import pytest

from backend.tests.architecture import module_map, rules, sql_scan
from backend.tests.architecture.test_ratchet import entries, growth_verdict

REPO = Path(__file__).resolve().parents[3]
BACKEND = REPO / 'backend'
ALLOWLIST = Path(__file__).with_name('allowlist.json')
ALLOWLIST_REL = 'backend/tests/architecture/allowlist.json'


def _allowlisted() -> set[tuple[str, str, str]]:
    data = json.loads(ALLOWLIST.read_text(encoding='utf-8'))
    return {(e['file'], e['table'], e['verb']) for e in data['sql_writes']}


@pytest.mark.Trait('Task', 'T305')
def test_real_writes_match_the_allowlist_exactly():
    found = rules.sql_violations(sql_scan.scan_writes(BACKEND))
    allowed = _allowlisted()
    new = sorted(found - allowed)
    stale = sorted(allowed - found)
    assert not new and not stale, (
        f'cross-module SQL writes differ from allowlist.json.\nnew: {new}\nstale, delete: {stale}'
    )


@pytest.mark.Trait('Task', 'T305')
def test_every_scanned_table_has_an_owner():
    tables = {t for _, t, _ in sql_scan.scan_writes(BACKEND)}
    assert tables <= set(rules.TABLE_OWNER), f'add to rules.TABLE_OWNER: {sorted(tables - set(rules.TABLE_OWNER))}'


@pytest.mark.Trait('Task', 'T305')
def test_schema_migrations_and_own_settings_writes_are_not_violations():
    writes = sql_scan.scan_writes(BACKEND)
    assert any(f == 'db/migrate.py' and t == 'schema_migrations' for f, t, _ in writes)
    assert any(f == 'routers/settings.py' and t == 'settings' for f, t, _ in writes)
    assert not [v for v in rules.sql_violations(writes) if v[0] in ('db/migrate.py', 'routers/settings.py')]


@pytest.mark.Trait('Task', 'T305')
def test_known_cross_module_writes_are_found():
    found = rules.sql_violations(sql_scan.scan_writes(BACKEND))
    for expected in [
        ('routers/devices.py', 'sos_alerts', 'DELETE'),
        ('routers/users.py', 'location_events', 'UPDATE'),   # found only by the multi-line scan
        ('routers/devices.py', 'fire_alerts', 'UPDATE'),
        ('main.py', 'users', 'INSERT'),
        ('hardware_reader/reader.py', 'location_events', 'INSERT'),
    ]:
        assert expected in found, expected
    assert not [v for v in found if v[0] == 'routers/locations.py']   # mapped to tracking and sos


@pytest.mark.Trait('Task', 'T305')
def test_scanner_finds_multiline_and_lowercase_sql(tmp_path):
    (tmp_path / 'routers').mkdir()
    (tmp_path / 'routers' / 'x.py').write_text(
        'SQL = """\n  update  devices\n  set x = 1"""\n'
        'A = "insert   into users (a) values (1)"\n'
        'B = """DELETE\n FROM groups WHERE id = 1"""\n'
        'C = "UPDATE sos_alerts s SET resolved = true"\n'
        'D = "SELECT * FROM users"\n',
        encoding='utf-8')
    assert sql_scan.scan_writes(tmp_path) == {
        ('routers/x.py', 'devices', 'UPDATE'), ('routers/x.py', 'users', 'INSERT'),
        ('routers/x.py', 'groups', 'DELETE'), ('routers/x.py', 'sos_alerts', 'UPDATE'),
    }


@pytest.mark.Trait('Task', 'T305')
def test_scanner_skips_tests_and_non_python(tmp_path):
    (tmp_path / 'tests').mkdir()
    (tmp_path / 'tests' / 't.py').write_text('X = "delete from users"', encoding='utf-8')
    (tmp_path / 'a.sql').write_text('delete from users', encoding='utf-8')
    assert sql_scan.scan_writes(tmp_path) == set()


@pytest.mark.Trait('Task', 'T305')
def test_scan_sql_outside_infrastructure_bites_on_a_toy_tree(tmp_path):
    mod = tmp_path / 'modules' / 'people'
    (mod / 'infrastructure' / 'deep').mkdir(parents=True)
    (mod / 'api.py').write_text('async def f(conn):\n    return await conn.fetch("select 1")\n', encoding='utf-8')
    (mod / 'service.py').write_text('async def g(conn):\n    await conn.execute("x")\n', encoding='utf-8')
    (mod / 'infrastructure' / 'repo.py').write_text('async def h(conn):\n    await conn.fetchrow("x")\n', encoding='utf-8')
    (mod / 'infrastructure' / 'deep' / 'r.py').write_text('async def i(conn):\n    await conn.fetchval("x")\n', encoding='utf-8')
    (tmp_path / 'routers').mkdir()
    (tmp_path / 'routers' / 'legacy.py').write_text('async def j(conn):\n    await conn.execute("x")\n', encoding='utf-8')
    assert sql_scan.scan_sql_outside_infrastructure(tmp_path) == {
        ('modules/people/api.py', 'fetch'), ('modules/people/service.py', 'execute'),
    }


@pytest.mark.Trait('Task', 'T305')
def test_no_sql_outside_infrastructure_in_the_real_modules():
    assert sql_scan.scan_sql_outside_infrastructure(BACKEND) == set()   # vacuous until step 1


@pytest.mark.Trait('Task', 'T305')
def test_allowlist_rows_are_complete_and_carry_the_owner_step():
    data = json.loads(ALLOWLIST.read_text(encoding='utf-8'))
    assert isinstance(data['completed_step'], int) and 0 <= data['completed_step'] <= 5
    for row in data['sql_writes']:
        assert set(row) == {'file', 'table', 'verb', 'until'}, row
        assert row['verb'] in ('INSERT', 'UPDATE', 'DELETE') and 1 <= row['until'] <= 5, row
        assert row['until'] == rules.until_step(row['file'], row['table']), row


@pytest.mark.Trait('Task', 'T305')
def test_until_follows_the_table_owner_and_the_override():
    assert rules.until_step('routers/devices.py', 'sos_alerts') == module_map.STEP_OF_MODULE['sos']
    assert rules.until_step('routers/users.py', 'location_events') == module_map.STEP_OF_MODULE['tracking']
    assert rules.until_step('main.py', 'users') == module_map.STEP_OVERRIDE['backend.main']


@pytest.mark.Trait('Task', 'T305')
def test_sql_allowlist_never_grows():
    status, msg = growth_verdict(ALLOWLIST_REL, 'json', REPO)
    if status == 'skip':
        pytest.skip(msg)
    assert status == 'ok', msg


@pytest.mark.Trait('Task', 'T305')
def test_sql_ratchet_compares_the_set_of_rows_not_the_count():
    a = json.dumps({'completed_step': 0, 'sql_writes': [{'file': 'a.py', 'table': 'x', 'verb': 'INSERT', 'until': 3}]})
    b = json.dumps({'completed_step': 0, 'sql_writes': [{'file': 'b.py', 'table': 'x', 'verb': 'INSERT', 'until': 3}]})
    assert len(entries(a, 'json')) == len(entries(b, 'json')) == 1
    assert entries(a, 'json') != entries(b, 'json')
