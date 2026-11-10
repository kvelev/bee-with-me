"""Ratchet on the import allowlist: it may shrink, never grow, and every line says when it must go."""
import json
import os
import re
import subprocess
import tomllib
from pathlib import Path

import pytest

from backend.tests.architecture import base_ref

REPO = Path(__file__).resolve().parents[3]
TOML = Path(__file__).with_name('importlinter.toml')
TOML_REL = 'backend/tests/architecture/importlinter.toml'


def count_entries(text: str, kind: str) -> int:
    """Total number of entries over all lists of an allowlist file (`kind` is 'toml' or 'json')."""
    if kind == 'toml':
        data = tomllib.loads(text)
        contracts = data.get('tool', {}).get('importlinter', {}).get('contracts', [])
        return sum(len(c.get('ignore_imports', [])) for c in contracts)
    if kind == 'json':
        data = json.loads(text)
        return sum(len(v) for v in data.values() if isinstance(v, list))
    raise ValueError(kind)


def entries(text: str, kind: str) -> set[str]:
    """The allowlist as a set of `<list owner>: <entry>` strings (contract name for toml, key for json).

    The ratchet compares sets, not counts: fixing one violation and adding another keeps the count equal.
    """
    if kind == 'toml':
        data = tomllib.loads(text)
        contracts = data.get('tool', {}).get('importlinter', {}).get('contracts', [])
        return {f"{c.get('name', '?')}: {e}" for c in contracts for e in c.get('ignore_imports', [])}
    if kind == 'json':
        data = json.loads(text)
        return {f'{k}: {json.dumps(e, sort_keys=True)}' for k, v in data.items() if isinstance(v, list) for e in v}
    raise ValueError(kind)


def _in_ci() -> bool:
    return bool(os.environ.get('CI') or os.environ.get('GITHUB_ACTIONS'))


def growth_verdict(rel: str, kind: str, cwd: Path) -> tuple[str, str]:
    """('ok'|'skip'|'fail', message): entries in `cwd` that the merge-base version does not have make it fail.

    No resolvable base is a visible skip locally and a failure in CI (a shallow checkout would otherwise turn the
    ratchet off without anyone noticing).
    """
    base = base_ref.resolve_base(cwd)
    if base is None:
        if _in_ci():
            return 'fail', ('no merge-base with ARCH_BASE_REF / upstream/develop / origin/develop in CI: '
                            'the checkout is shallow or the base branch is missing (use fetch-depth: 0)')
        return 'skip', 'no resolvable base ref (shallow clone or no upstream/origin develop): nothing to compare'
    old = base_ref.file_at_base(rel, cwd)
    if old is None:
        return 'skip', f'{rel} does not exist at the merge-base: this is its introduction'
    now = entries((cwd / rel).read_text(encoding='utf-8'), kind)
    before = entries(old, kind)
    added = sorted(now - before)
    if added:
        return 'fail', (f'{rel} has {len(added)} entr{"y" if len(added) == 1 else "ies"} the merge-base does not; '
                        f'the allowlist may only shrink. new: {added}')
    return 'ok', f'{rel}: {len(before)} -> {len(now)} entries'


def _ignore_lines() -> list[str]:
    data = tomllib.loads(TOML.read_text(encoding='utf-8'))
    return [e for c in data['tool']['importlinter']['contracts'] for e in c.get('ignore_imports', [])]


@pytest.mark.Trait('Task', 'T304')
def test_no_wildcards_in_ignore_imports():
    bad = [e for e in _ignore_lines() if '*' in e]
    assert not bad, f'wildcards hide new violations, list the edges one by one: {bad}'


@pytest.mark.Trait('Task', 'T304')
def test_allowlist_lines_carry_an_until_step():
    pattern = re.compile(r'^\s*"[^"]+"\s*,\s*#\s*until step ([1-5])\s*$')
    in_block = False
    missing = []
    for line in TOML.read_text(encoding='utf-8').splitlines():
        stripped = line.strip()
        if stripped.startswith('ignore_imports') and stripped.endswith('['):
            in_block = True
            continue
        if in_block and stripped == ']':
            in_block = False
            continue
        if in_block and stripped and not pattern.match(line):
            missing.append(line)
    assert not missing, f'every ignore_imports line needs "# until step N" (N 1..5): {missing}'


@pytest.mark.Trait('Task', 'T304')
def test_count_entries_counts_every_list():
    toml = '[[tool.importlinter.contracts]]\nignore_imports = ["a -> b", "c -> d"]\n[[tool.importlinter.contracts]]\nname = "x"\n'
    assert count_entries(toml, 'toml') == 2
    assert count_entries('{"completed_step": 0, "sql_writes": [1, 2, 3], "other": [4]}', 'json') == 4


@pytest.mark.Trait('Task', 'T304')
def test_allowlist_never_grows():
    status, msg = growth_verdict(TOML_REL, 'toml', REPO)
    if status == 'skip':
        pytest.skip(msg)
    assert status == 'ok', msg


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ['git', '-c', 'user.name=t', '-c', 'user.email=t@t', '-c', 'commit.gpgsign=false', *args],
        cwd=str(cwd), check=True, capture_output=True,
    )


def _toml(n: int) -> str:
    items = ', '.join(f'"a{i} -> b{i}"' for i in range(n))
    return f'[[tool.importlinter.contracts]]\nname = "c"\nignore_imports = [{items}]\n'


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    monkeypatch.delenv('ARCH_BASE_REF', raising=False)
    monkeypatch.delenv('CI', raising=False)
    monkeypatch.delenv('GITHUB_ACTIONS', raising=False)
    _git(tmp_path, 'init', '-b', 'main')
    return tmp_path


@pytest.mark.Trait('Task', 'T304')
def test_base_ref_logic_on_a_temp_git_repo(repo, monkeypatch):
    rel = 'allow.toml'
    # no base ref at all (no upstream/origin develop, no ARCH_BASE_REF)
    (repo / 'README').write_text('x')
    _git(repo, 'add', '.')
    _git(repo, 'commit', '-m', 'init')
    assert growth_verdict(rel, 'toml', repo)[0] == 'skip'
    assert 'no resolvable base' in growth_verdict(rel, 'toml', repo)[1]

    # base exists but the file does not: its introduction skips with that reason
    _git(repo, 'branch', 'base')
    monkeypatch.setenv('ARCH_BASE_REF', 'base')
    (repo / rel).write_text(_toml(3))
    _git(repo, 'add', '.')
    _git(repo, 'commit', '-m', 'introduce')
    status, msg = growth_verdict(rel, 'toml', repo)
    assert status == 'skip' and 'introduction' in msg

    # the file is on the base: equal passes, up fails, down passes
    _git(repo, 'branch', '-f', 'base', 'HEAD')
    assert growth_verdict(rel, 'toml', repo)[0] == 'ok'
    (repo / rel).write_text(_toml(4))
    status, msg = growth_verdict(rel, 'toml', repo)
    assert status == 'fail' and 'a3 -> b3' in msg
    (repo / rel).write_text(_toml(2))
    assert growth_verdict(rel, 'toml', repo)[0] == 'ok'


@pytest.mark.Trait('Task', 'T304')
def test_growth_compares_with_the_merge_base_not_the_tip(repo, monkeypatch):
    rel = 'allow.toml'
    (repo / rel).write_text(_toml(3))
    _git(repo, 'add', '.')
    _git(repo, 'commit', '-m', 'base state')
    _git(repo, 'branch', 'develop')
    _git(repo, 'checkout', '-b', 'feature')
    _git(repo, 'checkout', 'develop')
    (repo / rel).write_text(_toml(1))   # develop shrank after the branch point
    _git(repo, 'commit', '-am', 'develop shrinks')
    _git(repo, 'checkout', 'feature')
    monkeypatch.setenv('ARCH_BASE_REF', 'develop')
    (repo / rel).write_text(_toml(2))   # 2 > develop's 1, but < the merge-base's 3
    _git(repo, 'commit', '-am', 'feature shrinks a little')
    status, msg = growth_verdict(rel, 'toml', repo)
    assert status == 'ok', msg


@pytest.mark.Trait('Task', 'T304')
def test_remove_stale_deletes_only_stale_lines_and_adds_none(tmp_path):
    from backend.tests.architecture import regen
    from backend.tests.architecture.tooling import require_import_linter

    require_import_linter()   # regen runs import-linter

    text = TOML.read_text(encoding='utf-8')
    anchor = text.index('ignore_imports = [', text.index('id = "shims"')) + len('ignore_imports = [\n')
    stale = '    "backend.routers.groups -> backend.nothing_like_this",  # until step 4\n'
    cfg = tmp_path / 'copy.toml'
    cfg.write_text(text[:anchor] + stale + text[anchor:], encoding='utf-8')
    assert count_entries(cfg.read_text(encoding='utf-8'), 'toml') == count_entries(text, 'toml') + 1

    assert regen.remove_stale(cfg) == 0

    assert cfg.read_text(encoding='utf-8') == text   # exactly the original: only the stale line went
    # nothing in the CLI can add a line: the only modes are the read-only print and the deleting cleanup
    with pytest.raises(SystemExit):
        regen.main(['--add'])


def _toml_named(names: list[str]) -> str:
    items = ', '.join(f'"{n}"' for n in names)
    return f'[[tool.importlinter.contracts]]\nname = "c"\nignore_imports = [{items}]\n'


@pytest.fixture()
def ci_off(monkeypatch):
    monkeypatch.delenv('CI', raising=False)
    monkeypatch.delenv('GITHUB_ACTIONS', raising=False)


@pytest.mark.Trait('Task', 'T304')
def test_swapping_one_line_for_another_fails(repo, monkeypatch, ci_off):
    rel = 'allow.toml'
    (repo / rel).write_text(_toml_named(['a -> b', 'c -> d', 'e -> f']))
    _git(repo, 'add', '.')
    _git(repo, 'commit', '-m', 'base')
    _git(repo, 'branch', 'base')
    monkeypatch.setenv('ARCH_BASE_REF', 'base')
    # same count, one edge fixed and a different one added: unreviewed new debt
    (repo / rel).write_text(_toml_named(['a -> b', 'c -> d', 'x -> y']))
    status, msg = growth_verdict(rel, 'toml', repo)
    assert status == 'fail'
    assert 'x -> y' in msg and 'e -> f' not in msg.split('new:')[-1]


@pytest.mark.Trait('Task', 'T304')
def test_the_same_edge_under_another_contract_counts_as_new(repo, monkeypatch, ci_off):
    rel = 'allow.toml'
    two = ('[[tool.importlinter.contracts]]\nname = "one"\nignore_imports = ["a -> b"]\n'
           '[[tool.importlinter.contracts]]\nname = "two"\nignore_imports = []\n')
    moved = two.replace('["a -> b"]', '[]', 1).replace('name = "two"\nignore_imports = []', 'name = "two"\nignore_imports = ["a -> b"]')
    (repo / rel).write_text(two)
    _git(repo, 'add', '.')
    _git(repo, 'commit', '-m', 'base')
    _git(repo, 'branch', 'base')
    monkeypatch.setenv('ARCH_BASE_REF', 'base')
    (repo / rel).write_text(moved)
    assert growth_verdict(rel, 'toml', repo)[0] == 'fail'


@pytest.mark.Trait('Task', 'T304')
def test_shrinking_and_equal_sets_still_pass(repo, monkeypatch, ci_off):
    rel = 'allow.toml'
    (repo / rel).write_text(_toml_named(['a -> b', 'c -> d']))
    _git(repo, 'add', '.')
    _git(repo, 'commit', '-m', 'base')
    _git(repo, 'branch', 'base')
    monkeypatch.setenv('ARCH_BASE_REF', 'base')
    assert growth_verdict(rel, 'toml', repo)[0] == 'ok'
    (repo / rel).write_text(_toml_named(['c -> d']))
    assert growth_verdict(rel, 'toml', repo)[0] == 'ok'


@pytest.mark.Trait('Task', 'T304')
@pytest.mark.parametrize('var', ['CI', 'GITHUB_ACTIONS'])
def test_missing_base_ref_fails_loudly_in_ci(repo, monkeypatch, ci_off, var):
    (repo / 'README').write_text('x')
    _git(repo, 'add', '.')
    _git(repo, 'commit', '-m', 'init')
    assert growth_verdict('allow.toml', 'toml', repo)[0] == 'skip'   # locally: a visible skip
    monkeypatch.setenv(var, 'true')
    status, msg = growth_verdict('allow.toml', 'toml', repo)
    assert status == 'fail'
    assert 'fetch-depth: 0' in msg


@pytest.mark.Trait('Task', 'T304')
def test_a_new_file_at_a_resolvable_base_still_skips_in_ci(repo, monkeypatch, ci_off):
    (repo / 'README').write_text('x')
    _git(repo, 'add', '.')
    _git(repo, 'commit', '-m', 'init')
    _git(repo, 'branch', 'base')
    monkeypatch.setenv('ARCH_BASE_REF', 'base')
    monkeypatch.setenv('CI', 'true')
    (repo / 'allow.toml').write_text(_toml_named(['a -> b']))
    status, msg = growth_verdict('allow.toml', 'toml', repo)
    assert status == 'skip' and 'introduction' in msg
