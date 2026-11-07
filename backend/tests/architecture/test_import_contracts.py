"""Import contracts of the modular monolith, run through import-linter (decision: plan 2026-11-07, section 1)."""
import importlib
import itertools
import logging
import json
import re
import tomllib
from pathlib import Path

import pytest
from importlinter import cli

from backend.tests.architecture import module_map

REPO = Path(__file__).resolve().parents[3]
TOML = Path(__file__).with_name('importlinter.toml')
KNOWN_TOP_LEVEL = {'__init__', 'auth', 'config', 'database', 'json_columns', 'main', 'simulation', 'version', 'ws'}

# `no_cache=True` is the real switch: `cache_dir=None` means "use the default cache folder"
# (importlinter.cli._combine_caching_arguments), not "no cache".
NO_CACHE = {'no_cache': True}


def _config() -> dict:
    return tomllib.loads(TOML.read_text(encoding='utf-8'))['tool']['importlinter']


def _contracts() -> list[dict]:
    return _config()['contracts']


def _lint(config_path: Path, *contracts: str) -> int:
    """Run import-linter in-process without leaking its logging set-up into the rest of the session.

    lint_imports() calls logging.config.dictConfig(), whose default disable_existing_loggers=True silences every
    logger created before (backend.*), which empties caplog in all later tests. Snapshot and restore them.
    """
    root = logging.getLogger()
    saved = {n: (lg.disabled, lg.level, list(lg.handlers), lg.propagate)
             for n, lg in logging.root.manager.loggerDict.items() if isinstance(lg, logging.Logger)}
    root_state = (root.level, list(root.handlers))
    try:
        return cli.lint_imports(config_filename=str(config_path), limit_to_contracts=contracts, no_logo=True, **NO_CACHE)
    finally:
        for name, (disabled, level, handlers, propagate) in saved.items():
            lg = logging.getLogger(name)
            lg.disabled, lg.level, lg.handlers, lg.propagate = disabled, level, handlers, propagate
        root.level, root.handlers = root_state[0], root_state[1]


@pytest.mark.Trait('Task', 'T304')
def test_real_code_satisfies_all_contracts(monkeypatch):
    monkeypatch.chdir(REPO)
    assert _lint(TOML) == 0


# ── every contract bites ──────────────────────────────────────────────────────

_counter = itertools.count(1)


def _emit(value) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    return json.dumps(value)   # JSON strings and lists of strings are valid TOML


def _write(root: Path, rel: str, text: str = '') -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def _make(root: Path, dotted: str, body: str = '') -> None:
    """Create module `dotted` with __init__.py files for every parent package."""
    parts = dotted.split('.')
    for i in range(1, len(parts)):
        init = root.joinpath(*parts[:i], '__init__.py')
        if not init.exists():
            _write(root, '/'.join(parts[:i]) + '/__init__.py')
    package_init = root.joinpath(*parts, '__init__.py')
    if package_init.exists():   # already created as the parent of another module: keep it a package
        if body:
            package_init.write_text(body, encoding='utf-8')
        return
    _write(root, '/'.join(parts) + '.py', body)


def _swap(toy: str, text: str) -> str:
    return re.sub(r'^backend\b', toy, text)


def _build_toy(root: Path, toy: str, contract: dict) -> tuple[str, str]:
    """Toy package holding every module the contract names plus one violating import; returns (importer, imported)."""
    _write(root, f'{toy}/__init__.py')

    if contract['type'] == 'independence':
        a, b = (_swap(toy, contract['modules'][0]).replace('*', n) for n in ('a', 'b'))
        _make(root, b)
        _make(root, a, f'import {b}\n')
        return a, b

    sources = [_swap(toy, s).replace('*', 'x') for s in contract['source_modules']]
    forbidden = [_swap(toy, s).replace('*', 'x') for s in contract['forbidden_modules']]
    internal = [f for f in forbidden if f.split('.')[0] == toy]
    external = [f for f in forbidden if f.split('.')[0] != toy]
    for f in internal:
        _make(root, f)
    for s in sources[1:]:
        _make(root, s)
    imported = external[0] if external else internal[0]   # contracts that name an external package are fed that one
    _make(root, sources[0], f'import {imported}\n')
    return sources[0], imported


def _toy_toml(toy: str, contract: dict) -> str:
    lines = ['[tool.importlinter]', f'root_package = {_emit(toy)}',
             f'include_external_packages = {_emit(_config()["include_external_packages"])}',
             '', '[[tool.importlinter.contracts]]']
    for key, value in contract.items():
        if key == 'ignore_imports':
            continue   # the toy has no allowlist: the violation must show
        if isinstance(value, list):
            value = [_swap(toy, v) for v in value]
        lines.append(f'{key} = {_emit(value)}')
    return '\n'.join(lines) + '\n'


@pytest.mark.Trait('Task', 'T304')
@pytest.mark.parametrize('contract', _contracts(), ids=lambda c: c['name'])
def test_every_contract_bites(contract, tmp_path, monkeypatch, capsys):
    toy = f'toy_{next(_counter)}'
    importer, imported = _build_toy(tmp_path, toy, contract)
    cfg = tmp_path / 'toy.toml'
    cfg.write_text(_toy_toml(toy, contract), encoding='utf-8')
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.chdir(tmp_path)
    importlib.invalidate_caches()

    capsys.readouterr()
    result = _lint(cfg, contract['id'])
    out = capsys.readouterr().out

    assert result != 0, out
    assert 'BROKEN' in out and contract['name'] in out, out
    assert f'{importer} -> {imported}' in out, out


@pytest.mark.Trait('Task', 'T304')
def test_a_stale_allowlist_line_fails(tmp_path, monkeypatch, capsys):
    text = TOML.read_text(encoding='utf-8')
    marker = 'name = "legacy shims are not imported by production code"'
    assert marker in text
    anchor = text.index('ignore_imports = [', text.index(marker)) + len('ignore_imports = [')
    bogus = '\n    "backend.routers.groups -> backend.nothing_like_this",  # until step 4'
    cfg = tmp_path / 'stale.toml'
    cfg.write_text(text[:anchor] + bogus + text[anchor:], encoding='utf-8')
    monkeypatch.chdir(REPO)
    capsys.readouterr()
    result = _lint(cfg)
    out = capsys.readouterr().out
    assert result != 0
    assert 'No matches for ignored import' in out, out


# ── shape of the tree ─────────────────────────────────────────────────────────

@pytest.mark.Trait('Task', 'T304')
def test_top_level_modules_are_the_known_set():
    found = {p.stem for p in (REPO / 'backend').glob('*.py')}
    assert found == KNOWN_TOP_LEVEL, (
        f'new: {sorted(found - KNOWN_TOP_LEVEL)}, gone: {sorted(KNOWN_TOP_LEVEL - found)}; '
        'a new top-level module needs a conscious edit of the contracts and of this set'
    )


@pytest.mark.Trait('Task', 'T304')
def test_every_backend_file_is_in_the_module_map():
    unmapped = []
    for path in sorted((REPO / 'backend').rglob('*.py')):
        rel = path.relative_to(REPO / 'backend').as_posix()
        if rel.startswith('tests/'):
            continue
        try:
            module_map.owners_of(rel)
        except KeyError:
            unmapped.append(rel)
    assert not unmapped, f'add these files to module_map.MODULE_OF_FILE: {unmapped}'


@pytest.mark.Trait('Task', 'T304')
def test_owners_of_resolves_exact_prefix_and_modules_rule():
    assert module_map.owners_of('routers/locations.py') == ('tracking', 'sos')
    assert module_map.owners_of('fire/service.py') == ('fire',)
    assert module_map.owners_of('modules/settings/api.py') == ('settings',)
    assert module_map.owners_of('main.py') == ()
    assert module_map.owners_of('modules/__init__.py') == ('core',)
    with pytest.raises(KeyError):
        module_map.owners_of('brand_new.py')


@pytest.mark.Trait('Task', 'T304')
def test_linting_does_not_silence_other_loggers(monkeypatch, caplog):
    monkeypatch.chdir(REPO)
    probe = logging.getLogger('backend.t304_probe')
    assert _lint(TOML) == 0
    assert not probe.disabled
    with caplog.at_level(logging.WARNING, logger='backend.t304_probe'):
        probe.warning('still audible')
    assert 'still audible' in caplog.text
