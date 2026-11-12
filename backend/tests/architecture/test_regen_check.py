"""T600: `regen.py --check` is a dry run with an exit code, and both options list approvals whose row is gone."""
import json
from pathlib import Path

import pytest

from backend.tests.architecture import regen
from backend.tests.architecture.approved_additions import APPROVED
from backend.tests.architecture.tooling import require_import_linter

HERE = Path(__file__).parent
TOML_REL = 'backend/tests/architecture/importlinter.toml'
JSON_REL = 'backend/tests/architecture/allowlist.json'
STALE_TOML = '    "backend.routers.groups -> backend.nothing_like_this",  # until step 4\n'
STALE_EDGE = {'from': 'backend.routers.groups', 'to': 'backend.modules.no_such_module.api', 'until': 4}


@pytest.fixture
def copies(tmp_path):
    """Copies of the real importlinter.toml and allowlist.json, with one stale TOML line and two stale JSON rows."""
    require_import_linter()   # regen runs import-linter and grimp
    text = (HERE / 'importlinter.toml').read_text(encoding='utf-8')
    anchor = text.index('ignore_imports = [', text.index('id = "shims"')) + len('ignore_imports = [\n')
    cfg = tmp_path / 'copy.toml'
    cfg.write_text(text[:anchor] + STALE_TOML + text[anchor:], encoding='utf-8')
    data = json.loads((HERE / 'allowlist.json').read_text(encoding='utf-8'))
    data['sql_writes'].insert(0, {'file': 'routers/groups.py', 'table': 'no_such_table', 'verb': 'INSERT', 'until': 4})
    data['module_edges'].append(STALE_EDGE)
    allowlist = tmp_path / 'allowlist.json'
    allowlist.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return cfg, allowlist


def _clean(tmp_path):
    cfg = tmp_path / 'clean.toml'
    cfg.write_text((HERE / 'importlinter.toml').read_text(encoding='utf-8'), encoding='utf-8')
    allowlist = tmp_path / 'clean.json'
    allowlist.write_text((HERE / 'allowlist.json').read_text(encoding='utf-8'), encoding='utf-8')
    return cfg, allowlist


@pytest.mark.Trait("Task", "T600")
def test_check_writes_nothing_and_returns_1_for_a_stale_toml_line(tmp_path):
    require_import_linter()
    cfg, allowlist = _clean(tmp_path)
    text = cfg.read_text(encoding='utf-8')
    anchor = text.index('ignore_imports = [', text.index('id = "shims"')) + len('ignore_imports = [\n')
    cfg.write_text(text[:anchor] + STALE_TOML + text[anchor:], encoding='utf-8')
    before = (cfg.read_bytes(), allowlist.read_bytes())

    assert regen.check(cfg, allowlist) == 1

    assert (cfg.read_bytes(), allowlist.read_bytes()) == before


@pytest.mark.Trait("Task", "T600")
def test_check_returns_1_for_a_stale_json_row(copies):
    cfg, allowlist = copies
    clean = (HERE / 'importlinter.toml').read_text(encoding='utf-8')
    cfg.write_text(clean, encoding='utf-8')   # only the JSON rows are stale now
    before = allowlist.read_bytes()

    assert regen.check(cfg, allowlist) == 1

    assert allowlist.read_bytes() == before


@pytest.mark.Trait("Task", "T600")
def test_check_returns_0_and_prints_zero_when_nothing_is_stale(tmp_path, capsys):
    cfg, allowlist = _clean(tmp_path)

    assert regen.check(cfg, allowlist) == 0

    assert '0 stale line(s) found, 0 approval(s) to delete by hand' in capsys.readouterr().out


@pytest.mark.Trait("Task", "T600")
def test_check_prints_what_remove_stale_then_removes(copies, capsys):
    cfg, allowlist = copies

    assert regen.check(cfg, allowlist) == 1
    checked = capsys.readouterr().out
    assert regen.remove_stale(cfg, allowlist) == 0
    removed = capsys.readouterr().out

    found = [l.split('stale: ', 1)[1] for l in checked.splitlines() if l.startswith('stale: ')]
    gone = [l.split('removed stale: ', 1)[1] for l in removed.splitlines() if l.startswith('removed stale: ')]
    assert found and found == gone
    assert '3 stale line(s) found, 0 approval(s) to delete by hand' in checked
    assert '3 stale line(s) removed' in removed
    # after the removal the dry run is clean
    assert regen.check(cfg, allowlist) == 0


@pytest.mark.Trait("Task", "T600")
def test_a_stale_approval_is_listed_by_both_options_and_the_file_is_not_edited(tmp_path, capsys):
    cfg, allowlist = _clean(tmp_path)
    approved = {TOML_REL: {'module boundary: x: backend.a -> backend.b': 'an approval whose line is long gone'}}
    approvals_file = HERE / 'approved_additions.py'
    before = approvals_file.read_bytes()

    assert regen.check(cfg, allowlist, approved=approved) == 1
    out = capsys.readouterr().out
    assert f'approval to delete by hand: {TOML_REL}: module boundary: x: backend.a -> backend.b' in out
    assert '0 stale line(s) found, 1 approval(s) to delete by hand' in out

    assert regen.remove_stale(cfg, allowlist, approved=approved) == 0
    assert f'approval to delete by hand: {TOML_REL}: module boundary: x: backend.a -> backend.b' in capsys.readouterr().out
    assert approvals_file.read_bytes() == before


@pytest.mark.Trait("Task", "T600")
def test_an_approval_of_a_row_removed_in_the_same_run_is_listed(copies, capsys):
    cfg, allowlist = copies
    entry = f'module_edges: {json.dumps(STALE_EDGE, sort_keys=True)}'
    approved = {JSON_REL: {entry: 'approved once, and the row went away in this very run'}}

    assert regen.remove_stale(cfg, allowlist, approved=approved) == 0

    assert f'approval to delete by hand: {JSON_REL}: {entry}' in capsys.readouterr().out


@pytest.mark.Trait("Task", "T600")
def test_remove_stale_still_returns_0(copies):
    cfg, allowlist = copies

    assert regen.remove_stale(cfg, allowlist) == 0


@pytest.mark.Trait("Task", "T600")
def test_the_real_approvals_are_not_stale_on_the_real_tree():
    present = {
        TOML_REL: __import__('backend.tests.architecture.test_ratchet', fromlist=['entries']).entries(
            (HERE / 'importlinter.toml').read_text(encoding='utf-8'), 'toml'),
        JSON_REL: __import__('backend.tests.architecture.test_ratchet', fromlist=['entries']).entries(
            (HERE / 'allowlist.json').read_text(encoding='utf-8'), 'json'),
    }
    assert regen.stale_approvals(APPROVED, present) == []


@pytest.mark.Trait("Task", "T600")
def test_check_is_the_third_exclusive_option(monkeypatch):
    seen = []
    monkeypatch.setattr(regen, 'check', lambda *paths: seen.append(paths) or 1)
    assert regen.main(['--check']) == 1
    assert seen == [(regen.TOML, regen.ALLOWLIST)]
    with pytest.raises(SystemExit):
        regen.main(['--check', '--remove-stale'])


@pytest.mark.Trait("Task", "B140")
def test_an_approval_for_a_misspelled_file_is_stale():
    typo = 'backend/tests/architecture/alowlist.json'
    present = {TOML_REL: set(), JSON_REL: set()}
    assert regen.stale_approvals({typo: {'sql_writes: x': 'approved'}}, present) == [(typo, 'sql_writes: x')]


@pytest.mark.Trait("Task", "B140")
def test_a_known_file_that_was_not_read_is_still_not_judged():
    approved = {JSON_REL: {'sql_writes: x': 'approved'}}
    assert regen.stale_approvals(approved, {TOML_REL: set()}) == []      # --check without an allowlist


@pytest.mark.Trait("Task", "B140")
def test_check_fails_on_an_approval_for_a_misspelled_file(tmp_path, capsys):
    require_import_linter()
    cfg, allowlist = _clean(tmp_path)
    typo = 'backend/tests/architecture/importlinter.tml'
    assert regen.check(cfg, allowlist, approved={typo: {'x': 'approved'}}) == 1
    assert f'approval to delete by hand: {typo}: x' in capsys.readouterr().out


@pytest.mark.Trait("Task", "B140")
def test_main_has_two_blank_lines_before_it():
    assert '\n\n\ndef main(' in Path(regen.__file__).read_text(encoding='utf-8').replace('\r\n', '\n')
